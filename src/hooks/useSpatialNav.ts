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
 */

import { useCallback } from 'react';
import { useController, type Direction } from './useController';

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

export function useSpatialNav() {
  const onDirection = useCallback((dir: Direction) => {
    if (!dir) return;

    const current = document.activeElement;
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
    // Activate the focused element. We don't return early on a missing
    // activeElement up-front because we want the same shape as the
    // earlier handler — A on a non-HTMLElement target is just a no-op.
    const active = document.activeElement;
    if (active instanceof HTMLElement) active.click();
  }, []);

  useController(onButtonPress, onDirection);
}
