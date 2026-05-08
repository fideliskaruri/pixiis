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
 */

import { useCallback } from 'react';
import { useController, type Direction } from './useController';

// Anything that's natively focusable or opted-in via [data-focusable].
// Elements (or their ancestors) marked [data-no-spatial] are excluded
// — used by the top NavBar tabs so D-pad navigation is reserved for
// in-page content (page switching is handled by the LB/RB bumpers).
const FOCUSABLE_SELECTOR = '[data-focusable], button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])';

function isExcludedFromSpatial(el: Element): boolean {
  return el.closest('[data-no-spatial]') !== null;
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
    const active = document.activeElement;
    if (!active || !(active instanceof HTMLElement)) return;

    switch (button) {
      case 'a':
        // Activate the focused element
        active.click();
        break;
      case 'b': {
        // Navigate back — but skip when a modal is open. QuickResume,
        // VirtualKeyboard, and Lightbox each install their own B-button
        // handler to dismiss themselves; if the global handler also
        // fires, the user pops a route at the same time and lands two
        // surfaces deep in one press.
        const modalOpen = document.querySelector(
          '[role="dialog"][aria-modal="true"], [aria-modal="true"]',
        );
        if (modalOpen !== null) return;
        window.history.back();
        break;
      }
    }
  }, []);

  useController(onButtonPress, onDirection);
}
