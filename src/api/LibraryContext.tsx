/**
 * LibraryProvider — Single source of truth for the game list.
 *
 * Mounted once at the app root. Fetches `getLibrary()` on mount and on
 * `refresh()`. HomePage and GameDetailPage read this instead of calling
 * `getLibrary` themselves, so navigating tile → detail → back is
 * instant and the same fetch error is surfaced consistently.
 *
 * Auto-scan retry policy:
 *   When the persisted library returns empty on first load we trigger
 *   an auto-scan. If that scan rejects (transient panic in a provider,
 *   network glitch reaching a storefront API, etc.) we retry up to
 *   `MAX_AUTO_SCAN_ATTEMPTS` times with a `AUTO_SCAN_BACKOFF_MS` delay
 *   between attempts. The `autoScanAttempted` latch only flips once we
 *   either succeed or exhaust the budget — a bare-failure mount could
 *   never recover before, leaving Home empty until the user dug
 *   through Settings → Scan Now.
 *
 *   Two attempts is a deliberate floor: the first failure tends to be
 *   a cold-start race (steamapi reporting "not ready" on a fresh user
 *   session); a single retry covers that. We intentionally don't keep
 *   retrying forever — a persistent failure is surfaced as `'error'`
 *   so the user gets the inline retry button rather than a hidden loop.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { getLibrary, scanLibrary, type AppEntry } from './bridge';
import {
  applyProgressEvent,
  initialProviderRows,
  type ProviderRow,
} from '../components/scanProgressState';

type Status = 'idle' | 'loading' | 'auto-scanning' | 'ready' | 'error';

const MAX_AUTO_SCAN_ATTEMPTS = 2;
const AUTO_SCAN_BACKOFF_MS = 3000;

export interface LibraryState {
  games: AppEntry[];
  status: Status;
  error: string;
  refresh: () => void;
  /** O(1) lookup by entry id; recomputed when `games` changes. */
  byId: (id: string) => AppEntry | undefined;
  /** True while the provider is auto-scanning on first launch. */
  isAutoScanning: boolean;
  /**
   * Per-provider state derived from `library:scan:progress` events.
   * Always six rows long (one per known storefront) so consumers can
   * render the table even before the first event lands.
   */
  scanProviders: ProviderRow[];
}

const Ctx = createContext<LibraryState | null>(null);

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [games, setGames] = useState<AppEntry[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [scanProviders, setScanProviders] = useState<ProviderRow[]>(
    initialProviderRows,
  );
  // Latch — flips true once auto-scan succeeds OR we've exhausted the
  // retry budget so we don't loop forever on a hard failure. Outlives
  // reloadKey on purpose. Stays `false` while a retry is still pending,
  // so a transient glitch on the first attempt doesn't poison subsequent
  // mounts (e.g. the user closing and reopening the window).
  const autoScanAttempted = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: number | undefined;

    const runScan = (attempt: number): void => {
      setStatus('auto-scanning');
      // Reset the per-provider readout each time so a retry starts from a
      // clean slate ("queued" everywhere) instead of inheriting the
      // failure glyphs from the previous attempt.
      setScanProviders(initialProviderRows());
      scanLibrary()
        .then((scanned) => {
          if (cancelled) return;
          autoScanAttempted.current = true;
          setGames(scanned);
          setStatus('ready');
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          const msg = err instanceof Error ? err.message : String(err);
          if (attempt < MAX_AUTO_SCAN_ATTEMPTS) {
            // Schedule a retry — keep status at 'auto-scanning' so the
            // UI continues showing the discovery hint instead of
            // flashing an error state for the backoff window.
            retryTimer = window.setTimeout(() => {
              if (cancelled) return;
              runScan(attempt + 1);
            }, AUTO_SCAN_BACKOFF_MS);
          } else {
            // Out of attempts — surface the failure via the standard
            // error path; the inline Retry button calls refresh() which
            // resets the latch and restarts the loader.
            autoScanAttempted.current = true;
            setError(msg);
            setStatus('error');
          }
        });
    };

    setStatus('loading');
    setError('');
    getLibrary()
      .then((entries) => {
        if (cancelled) return;
        setGames(entries);
        // Auto-scan once on first launch when the persisted library is
        // empty — otherwise Home stays blank until the user discovers
        // the Settings → Scan button. The latch keeps us from re-running
        // when the user filters down to zero rows.
        if (entries.length === 0 && !autoScanAttempted.current) {
          runScan(1);
          return;
        }
        setStatus('ready');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus('error');
      });
    return () => {
      cancelled = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [reloadKey]);

  const refresh = useCallback(() => {
    // Reset the auto-scan latch so a manual retry from the inline error
    // surface can re-arm the auto-scan path on a still-empty library.
    autoScanAttempted.current = false;
    setReloadKey((n) => n + 1);
  }, []);

  // Auto-refresh whenever any scan completes, no matter who triggered it.
  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    void listen('library:scan:done', () => {
      setReloadKey((n) => n + 1);
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  // Mirror per-provider scan progress into context so HomePage (and any
  // future surface) can show the same magazine-style readout
  // OnboardingPage uses, without each consumer having to subscribe to
  // the Tauri event channel separately.
  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    void listen<{
      provider?: string;
      state?: string;
      count?: number;
      error?: string | null;
    }>('library:scan:progress', (event) => {
      setScanProviders((rows) => applyProgressEvent(rows, event.payload ?? {}));
    }).then((fn) => {
      unlisten = fn;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  const idIndex = useMemo(() => {
    const map = new Map<string, AppEntry>();
    for (const g of games) map.set(g.id, g);
    return map;
  }, [games]);

  const byId = useCallback((id: string) => idIndex.get(id), [idIndex]);

  const isAutoScanning = status === 'auto-scanning';

  const value = useMemo<LibraryState>(
    () => ({
      games,
      status,
      error,
      refresh,
      byId,
      isAutoScanning,
      scanProviders,
    }),
    [games, status, error, refresh, byId, isAutoScanning, scanProviders],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLibrary(): LibraryState {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error(
      'useLibrary() called outside <LibraryProvider> — wrap App in the provider.',
    );
  }
  return ctx;
}
