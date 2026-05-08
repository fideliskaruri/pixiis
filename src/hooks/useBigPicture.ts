/**
 * useBigPicture — global "couch mode" affordances.
 *
 * One hook, mounted once at the App root, that maintains:
 *
 *   • body.cursor-hidden — set when the gamepad has been used in the
 *     last GAMEPAD_RECENT_MS and the mouse hasn't moved in
 *     MOUSE_IDLE_MS. The CSS rule (in animations.css) flips
 *     `cursor: none`. Avoids the Big Picture annoyance of a stuck
 *     cursor pinned in the centre of the TV.
 *
 *   • body.is-fullscreen — mirrored from the Tauri window's fullscreen
 *     state. Listens to the matching events so toggles via F11 / the
 *     navbar double-click / config-on-launch all flow through.
 *
 * Self-contained — no provider, no context, no controller hook
 * coupling. We poll the Gamepad API for "any input in the last frame"
 * the same way useController does, but we don't subscribe to button
 * edges (cheaper and avoids stomping on consumer handlers).
 */

import { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';

const GAMEPAD_RECENT_MS = 5_000;
const MOUSE_IDLE_MS = 1_500;

interface PadSnapshot {
  buttons: number; // bitfield of pressed buttons
  axes: number;    // sum of |axis| values past deadzone
}

const AXIS_DEADZONE = 0.2;

function snapshotPads(): PadSnapshot {
  const pads = navigator.getGamepads();
  let buttons = 0;
  let axes = 0;
  for (const gp of pads) {
    if (gp === null) continue;
    for (let i = 0; i < gp.buttons.length && i < 32; i += 1) {
      if (gp.buttons[i]?.pressed === true) buttons |= 1 << i;
    }
    for (const a of gp.axes) {
      if (Math.abs(a) > AXIS_DEADZONE) axes += Math.abs(a);
    }
  }
  return { buttons, axes };
}

export function useBigPicture(): void {
  const [isFullscreen, setIsFullscreen] = useState(false);

  // ── Cursor-hide tracker ─────────────────────────────────────────────
  useEffect(() => {
    let lastGamepadInputAt = 0;
    let lastMouseMoveAt = performance.now();
    let prev = snapshotPads();
    let raf = 0;
    let cursorHidden = false;

    const apply = (hide: boolean): void => {
      if (hide === cursorHidden) return;
      cursorHidden = hide;
      document.body.classList.toggle('cursor-hidden', hide);
    };

    const onMouseMove = (): void => {
      lastMouseMoveAt = performance.now();
      apply(false);
    };
    const onMouseDown = onMouseMove;
    const onWheel = onMouseMove;

    const tick = (): void => {
      const now = performance.now();
      const cur = snapshotPads();
      if (cur.buttons !== prev.buttons || Math.abs(cur.axes - prev.axes) > 0.05) {
        lastGamepadInputAt = now;
      }
      prev = cur;

      const padRecent = now - lastGamepadInputAt < GAMEPAD_RECENT_MS;
      const mouseIdle = now - lastMouseMoveAt > MOUSE_IDLE_MS;
      apply(padRecent && mouseIdle);

      raf = requestAnimationFrame(tick);
    };

    window.addEventListener('mousemove', onMouseMove, { passive: true });
    window.addEventListener('mousedown', onMouseDown, { passive: true });
    window.addEventListener('wheel', onWheel, { passive: true });
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('wheel', onWheel);
      document.body.classList.remove('cursor-hidden');
    };
  }, []);

  // ── Fullscreen-state mirror ─────────────────────────────────────────
  // Surfaces the window's fullscreen state to both React (callers can
  // import `useWindowFullscreen`) and CSS (`body.is-fullscreen`).
  useEffect(() => {
    let cancelled = false;
    const win = getCurrentWindow();

    const sync = (fs: boolean): void => {
      if (cancelled) return;
      setIsFullscreen(fs);
      document.body.classList.toggle('is-fullscreen', fs);
    };

    void win.isFullscreen().then(sync);

    // Tauri 2 doesn't expose a dedicated onFullscreenChange listener,
    // but a fullscreen toggle always fires a Resized event — same
    // pattern NavBar uses for maximize tracking.
    const unlistenResized = win.onResized(() => {
      void win.isFullscreen().then(sync);
    });

    // Browser-level fullscreen change (rare in Tauri but cheap to wire).
    const onWebFs = (): void => {
      void win.isFullscreen().then(sync);
    };
    document.addEventListener('fullscreenchange', onWebFs);

    return () => {
      cancelled = true;
      void unlistenResized.then((fn) => fn());
      document.removeEventListener('fullscreenchange', onWebFs);
      document.body.classList.remove('is-fullscreen');
    };
  }, []);

  // Stash the latest fullscreen flag on a module-level subscriber list
  // so `useWindowFullscreen` can read it without a context. Kept simple:
  // a single mounted instance is the contract.
  useEffect(() => {
    fullscreenSubscribers.forEach((fn) => fn(isFullscreen));
  }, [isFullscreen]);

  // ── ui.scale → CSS custom property ──────────────────────────────────
  // Read the merged config once on mount and push `ui.scale` to the
  // root as `--ui-scale`. The body.is-fullscreen tile-size rules pick
  // it up so the couch-from-TV use case gets bigger targets without a
  // restart-required code path.
  useEffect(() => {
    let cancelled = false;
    interface UiCfg { ui?: { scale?: unknown } }
    void invoke<UiCfg>('config_get').then((cfg) => {
      if (cancelled) return;
      const raw = cfg?.ui?.scale;
      const scale =
        typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : 1.0;
      document.documentElement.style.setProperty('--ui-scale', String(scale));
    }, () => {
      // Config read failed — leave the CSS default (1.25) to apply.
    });
    return () => {
      cancelled = true;
    };
  }, []);
}

// ── useWindowFullscreen ──────────────────────────────────────────────
//
// Tiny pub-sub backing the boolean exported by useBigPicture so any
// component (NavBar, GameTile sizing) can observe fullscreen state
// without prop-drilling. The single source of truth is the latest
// value useBigPicture pushed; callers receive an initial value via
// the Tauri call and then live updates.

const fullscreenSubscribers = new Set<(fs: boolean) => void>();
let lastKnownFullscreen = false;

export function useWindowFullscreen(): boolean {
  const [fs, setFs] = useState(lastKnownFullscreen);
  useEffect(() => {
    const fn = (next: boolean): void => {
      lastKnownFullscreen = next;
      setFs(next);
    };
    fullscreenSubscribers.add(fn);
    // Pick up state immediately if useBigPicture already ran a sync.
    fn(lastKnownFullscreen);
    return () => {
      fullscreenSubscribers.delete(fn);
    };
  }, []);
  return fs;
}
