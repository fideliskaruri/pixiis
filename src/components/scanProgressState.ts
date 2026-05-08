/**
 * scanProgressState — Pure helpers + types for the ScanProgress
 * component. Split out of `ScanProgress.tsx` so the React-Refresh
 * `only-export-components` lint rule stays happy in the .tsx file.
 *
 * Anything in here is consumable by either onboarding (which manages
 * its own row list locally) or LibraryContext (which exposes the rows
 * to consumers via context), and never references React.
 */

import type { AppSource } from '../api/bridge';
import type { ProviderState } from '../api/types/ProviderState';

/** Display ordering for the provider list — same on every surface. */
const PROVIDERS: { key: AppSource; label: string }[] = [
  { key: 'steam', label: 'STEAM' },
  { key: 'xbox', label: 'XBOX' },
  { key: 'epic', label: 'EPIC' },
  { key: 'gog', label: 'GOG' },
  { key: 'ea', label: 'EA' },
  { key: 'startmenu', label: 'START MENU' },
];

/**
 * Local extension of the wire-format `ProviderState` with a `'pending'`
 * value the UI uses before the first event arrives for a provider.
 */
export type ProviderRowState = ProviderState | 'pending';

export interface ProviderRow {
  key: AppSource;
  label: string;
  state: ProviderRowState;
  count: number;
  detail?: string;
}

/** Build the initial six-row "queued" list shown before any event lands. */
export function initialProviderRows(): ProviderRow[] {
  return PROVIDERS.map(({ key, label }) => ({
    key,
    label,
    state: 'pending',
    count: 0,
  }));
}

/**
 * Merge a per-provider event payload into an existing rows list. Unknown
 * states fall back to `'pending'` so a future backend value never
 * crashes the UI.
 */
export function applyProgressEvent(
  rows: ProviderRow[],
  payload: { provider?: string; state?: string; count?: number; error?: string | null },
): ProviderRow[] {
  if (typeof payload.provider !== 'string') return rows;
  const state: ProviderRowState =
    payload.state === 'scanning' ||
    payload.state === 'done' ||
    payload.state === 'unavailable' ||
    payload.state === 'error'
      ? payload.state
      : 'pending';
  const count = typeof payload.count === 'number' ? payload.count : 0;
  const detail = payload.error ?? undefined;
  return rows.map((r) =>
    r.key === payload.provider ? { ...r, state, count, detail } : r,
  );
}

export function providerStateText(r: ProviderRow): string {
  switch (r.state) {
    case 'pending':
      return 'queued';
    case 'scanning':
      return 'scanning…';
    case 'done':
      return `${r.count} ${r.count === 1 ? 'game' : 'games'}`;
    case 'unavailable':
      return 'not detected';
    case 'error':
      return r.detail ?? 'failed';
  }
}
