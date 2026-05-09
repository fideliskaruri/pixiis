/**
 * useSpatialNav — Spatial navigation for controller D-pad.
 *
 * Finds the nearest focusable element in the pressed direction
 * and focuses it. Works with any DOM elements that have
 * [data-focusable] or are natively focusable (buttons, inputs).
 *
 * Usage:
 *   useSpatialNav(); // in your root component
 *   <div data-focusable tabIndex={0}>...</div>
 *
 * Buttons handled here:
 *   - A activates the focused element (`active.click()`).
 *   - B / LB / RB are intentionally NOT handled here. They're owned
 *     by `useBumperNav`, which has access to the current route — that's
 *     the only place that can decide "B on Home is a no-op" vs "B on
 *     /game/:id pops one level back".
 *
 * Per-component intercepts (controller-only papercuts):
 *   - `<input type="range">` focused: D-pad left/right adjusts the
 *     slider value (stepDown/stepUp + input/change events) instead of
 *     moving focus. D-pad up/down still escapes the slider — sliders
 *     are inherently 1-D so vertical traversal has nothing to lose.
 *   - `<select>` focused: A presses the focused element via
 *     `showPicker()` (Chromium 102+) so the native dropdown opens.
 *     Falls back to a synthetic mousedown for older webviews.
 *   - `[data-hold-to-activate]` focused: A press dispatches a
 *     synthetic pointerdown; A release dispatches pointerup. Lets
 *     buttons authored for press-and-hold (voice test, hold-to-buy)
 *     work from the gamepad without a custom hook in each consumer.
 *   - Text-style `<input>` focused: when the on-screen keyboard isn't
 *     mounted, A reopens it. Matches the user's "press A to type"
 *     mental model after they previously dismissed it with B.
 */

import { useCallback, useEffect, useRef } from 'react';
import { useController, type Direction } from './useController';
import { useVirtualKeyboard } from '../components/VirtualKeyboard';

// Anything that's natively focusable or opted-in via [data-focusable].
// Elements (or their ancestors) marked [data-no-spatial] are excluded
// — used by the top NavBar tabs so D-pad navigation is reserved for
// in-page content (page switching is handled by the LB/RB bumpers).
// Defensive secondary skip on `.navbar` descendants ensures D-pad
// never lands on the NavBar even if a future tab forgets the attr or
// a new chrome control renders without it.
const FOCUSABLE_SELECTOR = '[data-focusable], button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])';

function isExcludedFromSpatial(el: Element): boolean {
  if (el.closest('[data-no-spatial]') !== null) return true;
  if (el.closest('.navbar') !== null) return true;
  return false;
}

function getCenter(el: Element): { x: number; y: number } {
  const rect = el.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

function findNearest(current: Element, direction: Direction): Element | null {
  if (!direction) return null;

  const all = Array.from(document.querySelectorAll(FOCUSABLE_SELECTOR));
  const { x: cx, y: cy } = getCenter(current);

  let best: Element | null = null;
  let bestDist = Infinity;

  for (const candidate of all) {
    if (candidate === current) continue;
    if (!candidate.checkVisibility()) continue;
    if (isExcludedFromSpatial(candidate)) continue;

    const { x: tx, y: ty } = getCenter(candidate);

    // Direction filter
    const threshold = 5;
    if (direction === 'right' && tx <= cx + threshold) continue;
    if (direction === 'left' && tx >= cx - threshold) continue;
    if (direction === 'down' && ty <= cy + threshold) continue;
    if (direction === 'up' && ty >= cy - threshold) continue;

    // Weighted distance (prefer same row/column)
    const perpWeight = 3;
    let dist: number;
    if (direction === 'left' || direction === 'right') {
      dist = Math.abs(tx - cx) + Math.abs(ty - cy) * perpWeight;
    } else {
      dist = Math.abs(ty - cy) + Math.abs(tx - cx) * perpWeight;
    }

    if (dist < bestDist) {
      bestDist = dist;
      best = candidate;
    }
  }

  return best;
}

/** True iff the element is a slider (`<input type="range">`). */
function isRangeInput(el: Element | null): el is HTMLInputElement {
  return el instanceof HTMLInputElement && el.type === 'range';
}

/** True iff the element is a `<select>` we should open on A. */
function isSelectElement(el: Element | null): el is HTMLSelectElement {
  return el instanceof HTMLSelectElement;
}

/** True iff the element opted into hold-to-activate via the data attr. */
function hasHoldToActivate(el: Element | null): el is HTMLElement {
  return el instanceof HTMLElement && el.hasAttribute('data-hold-to-activate');
}

/**
 * True iff the element is a text-style input that should reopen the
 * on-screen keyboard on A. We restrict to text-like types so A on a
 * checkbox/radio still toggles via the default click path.
 */
function isTextLikeInput(el: Element | null): el is HTMLInputElement | HTMLTextAreaElement {
  if (el instanceof HTMLTextAreaElement) return true;
  if (el instanceof HTMLInputElement) {
    const t = el.type;
    return (
      t === 'text' ||
      t === 'search' ||
      t === 'email' ||
      t === 'url' ||
      t === 'tel' ||
      t === 'password' ||
      t === ''
    );
  }
  return false;
}

/**
 * Dispatch a synthetic PointerEvent on a target. Used by the
 * `data-hold-to-activate` path so existing onPointerDown / onPointerUp
 * handlers fire when A is pressed and released on the gamepad.
 *
 * Tauri's webview ships PointerEvent on every supported platform; we
 * pick PointerEvent over MouseEvent because every consumer in the
 * codebase that cares about hold-style input (Settings voice test) is
 * wired to onPointerDown / onPointerUp.
 */
function dispatchPointer(target: HTMLElement, type: 'pointerdown' | 'pointerup'): void {
  const rect = target.getBoundingClientRect();
  const evt = new PointerEvent(type, {
    bubbles: true,
    cancelable: true,
    composed: true,
    pointerType: 'mouse',
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
    button: 0,
    buttons: type === 'pointerdown' ? 1 : 0,
  });
  target.dispatchEvent(evt);
}

export function useSpatialNav() {
  // Track which element is currently mid-hold via A. The controller
  // hook only emits rising-edge button events, so we poll the gamepad
  // for A's release ourselves and dispatch pointerup on the same node
  // even if focus moved during the hold.
  const holdActiveRef = useRef<HTMLElement | null>(null);
  const vkbd = useVirtualKeyboard();

  const onDirection = useCallback((dir: Direction) => {
    if (!dir) return;

    const current = document.activeElement;

    // ── Slider intercept ──────────────────────────────────────────
    // D-pad left/right on a focused range input adjusts the value
    // instead of moving focus. Up/down still move focus — sliders
    // are 1-D so vertical traversal escapes them naturally.
    if (isRangeInput(current) && (dir === 'left' || dir === 'right')) {
      if (dir === 'left') {
        current.stepDown();
      } else {
        current.stepUp();
      }
      // `input` is the live event React's onChange listens for on
      // ranges; `change` is the commit event a11y tools expect.
      current.dispatchEvent(new Event('input', { bubbles: true }));
      current.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }

    if (!current || current === document.body) {
      // Nothing focused — focus the first non-excluded focusable.
      const candidates = document.querySelectorAll(FOCUSABLE_SELECTOR);
      for (const el of Array.from(candidates)) {
        if (isExcludedFromSpatial(el)) continue;
        if (el instanceof HTMLElement) {
          el.focus();
          break;
        }
      }
      return;
    }

    const next = findNearest(current, dir);
    if (next instanceof HTMLElement) {
      next.focus();
      // Scroll into view smoothly
      next.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
  }, []);

  const onButtonPress = useCallback((button: string) => {
    if (button !== 'a') return;
    const active = document.activeElement;

    // ── Hold-to-activate ──────────────────────────────────────────
    // Fire synthetic pointerdown so the existing onPointerDown
    // handler on the focused element trips. We track the held
    // element so the falling-edge poll fires pointerup on the same
    // node — even if the user's focus drifts during the hold.
    if (hasHoldToActivate(active)) {
      holdActiveRef.current = active;
      dispatchPointer(active, 'pointerdown');
      return;
    }

    // ── Select dropdown ───────────────────────────────────────────
    // A on a `<select>` should open it. `showPicker()` is the clean
    // Chromium 102+ path; Tauri's webview is well past that. The
    // synthetic mousedown fallback keeps older webviews working.
    if (isSelectElement(active)) {
      type SelectWithPicker = HTMLSelectElement & { showPicker?: () => void };
      const selectEl = active as SelectWithPicker;
      if (typeof selectEl.showPicker === 'function') {
        try {
          selectEl.showPicker();
          return;
        } catch {
          // Fall through to mousedown — showPicker can throw if the
          // element isn't focusable yet (e.g. mid-render).
        }
      }
      const evt = new MouseEvent('mousedown', {
        bubbles: true,
        cancelable: true,
        composed: true,
        button: 0,
        buttons: 1,
      });
      active.dispatchEvent(evt);
      return;
    }

    // ── Text input → reopen keyboard ──────────────────────────────
    // If the on-screen keyboard isn't mounted (the user dismissed it
    // with B and now wants it back), reopen it. When the keyboard is
    // already mounted, A on the input is a no-op and the keyboard
    // handles its own internal nav.
    if (isTextLikeInput(active)) {
      if (!vkbd.isOpen) {
        vkbd.reopen(active);
        return;
      }
      // Keyboard already open — fall through. click() on a text
      // input is a no-op which preserves prior behavior.
    }

    // Default: synthesize a click on the focused element.
    if (active instanceof HTMLElement) active.click();
  }, [vkbd]);

  useController(onButtonPress, onDirection);

  // ── Hold-to-activate falling edge ────────────────────────────────
  // useController only emits rising-edge button events. Run our own
  // RAF loop and watch button 0 (A) for release so the matching
  // pointerup fires on the held node. Cost is one extra
  // `navigator.getGamepads()` per frame.
  useEffect(() => {
    let raf = 0;
    let cancelled = false;
    const tick = (): void => {
      if (cancelled) return;
      const gp = navigator.getGamepads()[0];
      const aPressed = gp?.buttons[0]?.pressed ?? false;
      const held = holdActiveRef.current;
      if (held !== null && !aPressed) {
        dispatchPointer(held, 'pointerup');
        holdActiveRef.current = null;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, []);
}
