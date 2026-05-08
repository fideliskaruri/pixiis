/**
 * useAutoFocus — Land focus on a target selector after the page mounts.
 *
 * Controllers don't have a "tab to first thing" affordance; without an
 * explicit focus on each route mount, D-pad navigation finds nothing
 * focused, falls back to the first focusable element document-wide
 * (which can be a navbar control), and the user has to flick around
 * before anything visibly responds.
 *
 * Pages that want auto-focus pass a CSS selector and an optional deps
 * array (so they can re-focus after async data loads — e.g. a Library
 * page that mounts before its grid renders). The query runs inside a
 * requestAnimationFrame so the DOM is laid out before we look at it.
 */

import { useEffect } from 'react';

export function useAutoFocus(
  selector: string,
  deps: ReadonlyArray<unknown> = [],
): void {
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(selector);
      target?.focus();
    });
    return () => cancelAnimationFrame(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
