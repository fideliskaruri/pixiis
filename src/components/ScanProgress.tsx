/**
 * ScanProgress — Magazine-style provider-by-provider scan readout.
 *
 * Shared between Onboarding (first-launch walkthrough) and Home (when
 * the LibraryContext is auto-scanning on first launch). The
 * presentation is styled in `OnboardingPage.css` under the
 * `onboarding__provider-*` selectors so the two surfaces stay visually
 * identical without duplicating CSS.
 *
 * The component is purely presentational: it reads a list of provider
 * rows and a "is the overall scan still running" hint, and renders the
 * status glyph + count for each. State management (subscribing to the
 * `library:scan:progress` event channel, deriving fallbacks when the
 * backend never emitted a per-provider event) lives in callers — most
 * notably `LibraryContext`, which now exposes `scanProviders`.
 *
 * Pure helpers (`initialProviderRows`, `applyProgressEvent`, the
 * `ProviderRow` type) live in `./scanProgressState` so this file can
 * keep its components-only export list and play nicely with Vite's
 * fast-refresh boundary.
 */

import {
  providerStateText,
  type ProviderRow,
  type ProviderRowState,
} from './scanProgressState';

interface ScanProgressProps {
  rows: ProviderRow[];
  /** Hint that the overall scan is still in flight — drives the spinner glyph. */
  scanning?: boolean;
}

export function ScanProgress({ rows, scanning = false }: ScanProgressProps) {
  return (
    <ul
      className="onboarding__provider-list"
      role="list"
      aria-live="polite"
      aria-busy={scanning}
    >
      {rows.map((r) => (
        <li key={r.key} className="onboarding__provider-row">
          <span className="label onboarding__provider-name">{r.label}</span>
          <span className="onboarding__provider-state">
            <ProviderGlyph state={r.state} />
            <span className="onboarding__provider-text">
              {providerStateText(r)}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function ProviderGlyph({ state }: { state: ProviderRowState }) {
  if (state === 'done') {
    return (
      <span className="onboarding__glyph onboarding__glyph--ok" aria-hidden>
        ✓
      </span>
    );
  }
  if (state === 'unavailable') {
    return (
      <span className="onboarding__glyph onboarding__glyph--mute" aria-hidden>
        —
      </span>
    );
  }
  if (state === 'error') {
    return (
      <span className="onboarding__glyph onboarding__glyph--err" aria-hidden>
        ✕
      </span>
    );
  }
  if (state === 'scanning') {
    return (
      <span className="onboarding__glyph onboarding__glyph--spin" aria-hidden>
        ⠿
      </span>
    );
  }
  return (
    <span className="onboarding__glyph onboarding__glyph--mute" aria-hidden>
      ·
    </span>
  );
}
