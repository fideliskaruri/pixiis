/**
 * useBumperNav — LB / RB cycle through the top-level pages, plus
 * route-aware B-button back navigation.
 *
 * D-pad on the controller is reserved for in-page spatial navigation
 * (focus-walking through tiles, chips, buttons). The shoulder bumpers
 * own page-level navigation so the user never has to land on the
 * NavBar tabs to switch surfaces. NavBar tabs carry [data-no-spatial]
 * and remain mouse-clickable; the bumpers are the controller path.
 *
 * Behaviour:
 *   - RB: next page in [/, /library, /settings]; wraps at the end.
 *   - LB: previous page; wraps at the start.
 *   - On non-top-level routes (/game/:id, /files, /onboarding) the
 *     bumpers are no-ops — the user is somewhere modal-ish and we
 *     don't want a stray shoulder-button press to evict them.
 *
 * B button:
 *   - On /game/:id, B = `navigate(-1)` (history back).
 *   - On any top-level route, B is a no-op so the user can't
 *     accidentally back out of the entire app shell.
 *   - When a true modal is open (`aria-modal="true"`), the modal owns
 *     its own dismiss; we bypass and let it handle the press.
 *
 * Mount once globally from App. Internally subscribes to useController.
 */

import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useController, type ControllerButton } from './useController';

const TOP_LEVEL: ReadonlyArray<string> = ['/', '/library', '/settings'];

function isTopLevel(pathname: string): boolean {
  return TOP_LEVEL.includes(pathname);
}

function isGameDetail(pathname: string): boolean {
  return pathname.startsWith('/game/');
}

function modalIsOpen(): boolean {
  // Match the same selector useSpatialNav uses for B-button bypass so
  // the two stay in agreement about what "modal" means. VirtualKeyboard
  // is intentionally aria-modal="false" — it installs its own
  // useController listener and handles B itself.
  return (
    document.querySelector('[role="dialog"][aria-modal="true"], [aria-modal="true"]') !== null
  );
}

export function useBumperNav(): void {
  const navigate = useNavigate();
  const location = useLocation();

  const onButtonPress = useCallback(
    (button: ControllerButton) => {
      // Don't compete with an open overlay — QuickResume, QuickSearch,
      // ShortcutsCheatSheet, the Lightbox all install handlers that
      // expect to own the press while they're up.
      if (modalIsOpen()) return;

      const path = location.pathname;

      if (button === 'rb' || button === 'lb') {
        if (!isTopLevel(path)) return; // bumpers no-op outside top-level
        const idx = TOP_LEVEL.indexOf(path);
        const next =
          button === 'rb'
            ? TOP_LEVEL[(idx + 1) % TOP_LEVEL.length]
            : TOP_LEVEL[(idx - 1 + TOP_LEVEL.length) % TOP_LEVEL.length];
        if (next !== undefined && next !== path) navigate(next);
        return;
      }

      if (button === 'b') {
        // Top-level pages: B is a no-op so users can't accidentally
        // back out of the app shell.
        if (isTopLevel(path)) return;
        if (isGameDetail(path)) {
          navigate(-1);
        }
        // Other non-top-level routes (/files, /onboarding) intentionally
        // don't pop — onboarding has its own flow control, and /files
        // is a long-lived utility surface where back-stack semantics
        // would be surprising.
      }
    },
    [navigate, location.pathname],
  );

  useController(onButtonPress);
}
