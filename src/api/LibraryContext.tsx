/**
 * LibraryProvider — Single source of truth for the game list.
 *
 * Mounted once at the app root. Fetches `getLibrary()` on mount and on
 * `refresh()`. HomePage and GameDetailPage read this instead of calling
 * `getLibrary` themselves, so navigating tile → detail → back is
 * instant and the same fetch error is surfaced consistently.
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

type Status = 'idle' | 'loading' | 'ready' | 'error';

export interface LibraryState {
  games: AppEntry[];
  status: Status;
  error: string;
  refresh: () => void;
  /** O(1) lookup by entry id; recomputed when `games` changes. */
  byId: (id: string) => AppEntry | undefined;
}

const Ctx = createContext<LibraryState | null>(null);

export function LibraryProvider({ children }: { children: ReactNode }) {
  const [games, setGames] = useState<AppEntry[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  // Auto-scan is rate-limited rather than one-shot: a transient first
  // failure (network, cold storefront cache) shouldn't permanently
  // disable the silent first-launch scan. We allow up to MAX_AUTO_SCAN
  // attempts, only counting an attempt when it actually fired (and
  // counting on success too, so subsequent loads don't re-scan).
  const autoScanCount = useRef(0);
  const MAX_AUTO_SCAN = 3;

  useEffect(() => {
    // First-launch auto-scan is owned by /onboarding's LibraryScanStep —
    // the provider must not race it with a parallel scan, otherwise the
    // backend serialises them and one report displaces the other. The
    // provider still fetches the persisted list so the post-onboarding
    // navigation lands on a populated Home.
    const onOnboarding =
      typeof window !== 'undefined' &&
      window.location.pathname === '/onboarding';

    let cancelled = false;
    setStatus('loading');
    setError('');
    getLibrary()
      .then((entries) => {
        if (cancelled) return;
        setGames(entries);
        // Auto-scan when the persisted library is empty — otherwise Home
        // stays blank until the user discovers the Settings → Scan
        // button. Skip while onboarding owns the scan flow.
        if (
          entries.length === 0 &&
          !onOnboarding &&
          autoScanCount.current < MAX_AUTO_SCAN
        ) {
          autoScanCount.current += 1;
          setStatus('loading');
          scanLibrary()
            .then((scanned) => {
              if (cancelled) return;
              setGames(scanned);
              setStatus('ready');
              // Successful scan — pin the counter at the cap so we don't
              // try again on later refresh()es that happen to land on an
              // empty list (e.g. user uninstalled everything).
              autoScanCount.current = MAX_AUTO_SCAN;
            })
            .catch((err: unknown) => {
              if (cancelled) return;
              setError(err instanceof Error ? err.message : String(err));
              setStatus('error');
            });
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
    };
  }, [reloadKey]);

  const refresh = useCallback(() => {
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

  const idIndex = useMemo(() => {
    const map = new Map<string, AppEntry>();
    for (const g of games) map.set(g.id, g);
    return map;
  }, [games]);

  const byId = useCallback((id: string) => idIndex.get(id), [idIndex]);

  const value = useMemo<LibraryState>(
    () => ({ games, status, error, refresh, byId }),
    [games, status, error, refresh, byId],
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
