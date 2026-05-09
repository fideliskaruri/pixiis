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

/**
 * Read the integer row index baked onto a tile via `data-grid-row`.
 * Returns null when the attribute is absent or unparseable — toolbar
 * controls, rails, and detail-page buttons fall through to the purely
 * geometric scoring below. Wave 5 § 5.5.
 */
function getGridRow(el: Element): number | null {
  const raw = el.getAttribute('data-grid-row');
  if (raw === null) return null;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

function findNearest(current: Element, direction: Direction): Element | null {
  if (!direction) return null;

  const all = Array.from(document.querySelectorAll(FOCUSABLE_SELECTOR));
  const { x: cx, y: cy } = getCenter(current);
  const currentRow = getGridRow(current);
  const isVertical = direction === 'up' || direction === 'down';

  let best: Element | null = null;
  let bestDist = Infinity;
  // Row-aware tier: when both current and candidate have a grid-row,
  // candidates whose absolute row delta is exactly 1 in the move
  // direction (down → row+1, up → row-1) outrank candidates 2+ rows
  // away even if the further-away tile sits closer to our column. The
  // tier number is the absolute row delta; 0 = "best tier" and means
  // we have a row+1 candidate. Lower tier wins; ties break on
  // weighted geometric distance below. Non-grid candidates (no row
  // attribute) get tier MAX_SAFE_INTEGER and only win if no grid
  // candidate exists.
  let bestTier = Number.MAX_SAFE_INTEGER;

  for (const candidate of all) {
    if (candidate === current) continue;
    if (!candidate.checkVisibility()) continue;
    if (isExcludedFromSpatial(candidate)) continue;

    const { x: tx, y: ty } = getCenter(candidate);

    // Direction filter — strict half-plane. With this in place, the
    // grid never wraps screen edges: at the rightmost column there is
    // no candidate with tx > cx, so findNearest returns null and the
    // hook leaves focus put. Same logic on the other three edges.
    const threshold = 5;
    if (direction === 'right' && tx <= cx + threshold) continue;
    if (direction === 'left' && tx >= cx - threshold) continue;
    if (direction === 'down' && ty <= cy + threshold) continue;
    if (direction === 'up' && ty >= cy - threshold) continue;

    // Compute the row tier for vertical moves. Horizontal moves
    // (left/right) keep the legacy purely-geometric scoring — no
    // benefit from row tiering when we're not crossing rows.
    let tier = 0;
    if (isVertical && currentRow !== null) {
      const candRow = getGridRow(candidate);
      if (candRow === null) {
        // Toolbar / non-grid focusable above or below the grid — keep
        // it eligible but rank it below same-grid candidates.
        tier = Number.MAX_SAFE_INTEGER;
      } else {
        const delta = direction === 'down' ? candRow - currentRow : currentRow - candRow;
        // Negative delta = same direction but wrong sign (e.g. a tile
        // visually below in DOM but above in grid order due to
        // wrapping). Drop those — half-plane filter already excluded
        // anything geometrically wrong; this just guards mismatched
        // row attributes from sneaking in.
        if (delta <= 0) continue;
        tier = delta - 1; // 0 means "row N+1 / row N-1": ideal
      }
    }

    // Weighted distance (prefer same row/column)
    const perpWeight = 3;
    let dist: number;
    if (direction === 'left' || direction === 'right') {
      dist = Math.abs(tx - cx) + Math.abs(ty - cy) * perpWeight;
    } else {
      dist = Math.abs(ty - cy) + Math.abs(tx - cx) * perpWeight;
    }

    if (tier < bestTier || (tier === bestTier && dist < bestDist)) {
      bestTier = tier;
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
