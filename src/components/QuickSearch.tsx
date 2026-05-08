/**
 * QuickSearch — Global search modal.
 *
 * Universally accessible: gamepad X opens it from any page; Ctrl+K /
 * Cmd+K is the keyboard equivalent. Type → live filter against library
 * names → Enter launches the top hit (or the active row); Esc / B
 * closes. The provider must sit inside <LibraryProvider> so the modal
 * can read the canonical library list without triggering a fresh fetch.
 *
 * Editorial style: heavy black scrim (matches QuickResume's 80%), serif
 * column heading, small-caps source/playtime metadata. No glass, no
 * spring on the row-focus highlight — same 200ms ease-in-out.
 *
 * Gamepad event interception:
 *   While the panel is open, the polling controller hook is mounted
 *   *inside* this component. The panel's local handlers consume D-pad +
 *   A/B/Y; the rest of the app's controller listeners still fire (they
 *   no-op when document.activeElement isn't a focusable in their tree),
 *   so the cost of "swallowing" inputs lives entirely in render-time
 *   short-circuits inside the panel.
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
import { useNavigate } from 'react-router-dom';
import { useController } from '../hooks/useController';
import { useLibrary } from '../api/LibraryContext';
import { imageUrl, launchGame, type AppEntry } from '../api/bridge';
import { useToast } from '../api/ToastContext';
import './QuickSearch.css';

interface QuickSearchApi {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const Ctx = createContext<QuickSearchApi | null>(null);

export function useQuickSearch(): QuickSearchApi {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error(
      'useQuickSearch() called outside <QuickSearchProvider> — mount it at the app root.',
    );
  }
  return ctx;
}

const SOURCE_LABELS: Record<AppEntry['source'], string> = {
  steam: 'STEAM',
  xbox: 'XBOX',
  epic: 'EPIC',
  gog: 'GOG',
  ea: 'EA',
  startmenu: 'PC',
  manual: 'CUSTOM',
  folder: 'PC',
};

const MAX_RESULTS = 12;

export function QuickSearchProvider({ children }: { children?: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const open = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);

  const api = useMemo<QuickSearchApi>(
    () => ({ open, close, isOpen }),
    [open, close, isOpen],
  );

  // Global X button (gamepad) and Ctrl+K (keyboard) open the modal.
  // While open, the panel's own listeners take over and the global
  // handler returns early so X doesn't immediately re-toggle off.
  useController(
    useCallback(
      (button) => {
        if (isOpen) return;
        if (button === 'x') setOpen(true);
      },
      [isOpen],
    ),
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      // Ctrl+K / Cmd+K — universal "command palette" muscle memory.
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <Ctx.Provider value={api}>
      {children}
      {isOpen && <Panel onClose={close} />}
    </Ctx.Provider>
  );
}

interface PanelProps {
  onClose: () => void;
}

function Panel({ onClose }: PanelProps) {
  const { games } = useLibrary();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const [launching, setLaunching] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const restoreFocus = useRef<Element | null>(null);

  // Save the prior focus so we can restore it on close (matches
  // QuickResume's pattern — keeps controller / keyboard users where
  // they were before the modal opened).
  useEffect(() => {
    restoreFocus.current = document.activeElement;
    // Auto-focus the input on mount so typing starts immediately —
    // requestAnimationFrame avoids losing focus to the page's spatial
    // nav restore on first paint.
    const id = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(id);
      const el = restoreFocus.current;
      if (el instanceof HTMLElement) el.focus();
    };
  }, []);

  const results = useMemo<AppEntry[]>(() => {
    const games_only = games.filter((g) => g.is_game);
    if (query.trim() === '') {
      // Empty query: show recently played first, then alpha — gives the
      // user something to act on the moment they open the panel.
      return games_only
        .slice()
        .sort((a, b) => {
          if (a.last_played !== b.last_played) return b.last_played - a.last_played;
          return a.name.localeCompare(b.name);
        })
        .slice(0, MAX_RESULTS);
    }
    const q = query.toLowerCase();
    // Score: prefix match > word-start match > substring. Keeps
    // "wat" → "Watch Dogs" above "Skywatcher" in the typical case.
    type Scored = { game: AppEntry; score: number };
    const scored: Scored[] = [];
    for (const g of games_only) {
      const name = g.name.toLowerCase();
      if (name.startsWith(q)) scored.push({ game: g, score: 0 });
      else if (name.includes(' ' + q) || name.includes('-' + q)) {
        scored.push({ game: g, score: 1 });
      } else if (name.includes(q)) scored.push({ game: g, score: 2 });
    }
    scored.sort((a, b) => {
      if (a.score !== b.score) return a.score - b.score;
      return a.game.name.localeCompare(b.game.name);
    });
    return scored.slice(0, MAX_RESULTS).map((s) => s.game);
  }, [games, query]);

  // Keep the active row inside the result range as the list shrinks.
  useEffect(() => {
    if (active >= results.length) setActive(0);
  }, [results, active]);

  const launch = useCallback(
    async (game: AppEntry): Promise<void> => {
      if (launching !== null) return;
      setLaunching(game.id);
      try {
        await launchGame(game.id);
        toast(`Launching ${game.name}`, 'success');
        onClose();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        toast(`Failed to launch: ${msg}`, 'error');
        setLaunching(null);
      }
    },
    [launching, onClose, toast],
  );

  const openDetail = useCallback(
    (game: AppEntry): void => {
      onClose();
      navigate(`/game/${encodeURIComponent(game.id)}`);
    },
    [navigate, onClose],
  );

  // Keyboard: Esc closes, arrows move, Enter launches active result.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActive((i) => Math.min(Math.max(0, results.length - 1), i + 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const game = results[active];
        if (game !== undefined) void launch(game);
      }
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [results, active, launch, onClose]);

  // Controller while open: D-pad up/down moves, A launches, B/X close,
  // Y opens detail. The X-to-toggle in the provider is suppressed while
  // open via the `isOpen` early return there.
  useController(
    useCallback(
      (button) => {
        if (button === 'b' || button === 'x') {
          onClose();
        } else if (button === 'a') {
          const game = results[active];
          if (game !== undefined) void launch(game);
        } else if (button === 'y') {
          const game = results[active];
          if (game !== undefined) openDetail(game);
        }
      },
      [results, active, launch, openDetail, onClose],
    ),
    useCallback(
      (dir) => {
        if (dir === 'down') {
          setActive((i) => Math.min(Math.max(0, results.length - 1), i + 1));
        } else if (dir === 'up') {
          setActive((i) => Math.max(0, i - 1));
        }
      },
      [results.length],
    ),
  );

  return (
    <div
      className="qsearch fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Quick Search"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="qsearch__panel">
        <header className="qsearch__head">
          <p className="label">SEARCH</p>
          <input
            ref={inputRef}
            type="text"
            className="qsearch__input"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Type to filter your library…"
            aria-label="Search library"
            data-focusable
            spellCheck={false}
            autoComplete="off"
          />
        </header>

        <div className="qsearch__results" role="listbox">
          {results.length === 0 ? (
            <p className="qsearch__empty">
              {query.trim() === ''
                ? 'Your library is empty.'
                : `No matches for “${query}”.`}
            </p>
          ) : (
            results.map((game, i) => {
              const sourceLabel =
                SOURCE_LABELS[game.source] ?? game.source.toUpperCase();
              const art = imageUrl(game.art_url);
              const isActive = i === active;
              const isLaunching = launching === game.id;
              return (
                <button
                  key={game.id}
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  className={`qsearch__row ${isActive ? 'qsearch__row--active' : ''}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => void launch(game)}
                  disabled={launching !== null && launching !== game.id}
                  data-focusable
                >
                  <div className="qsearch__art">
                    {art !== '' && <img src={art} alt="" loading="lazy" />}
                  </div>
                  <div className="qsearch__meta">
                    <p className="label qsearch__source">{sourceLabel}</p>
                    <p className="qsearch__name">{game.name}</p>
                  </div>
                  {game.playtime_display !== '' && (
                    <p className="label qsearch__playtime">
                      {game.playtime_display.toUpperCase()}
                    </p>
                  )}
                  {isLaunching && (
                    <p className="label qsearch__status">LAUNCHING…</p>
                  )}
                </button>
              );
            })
          )}
        </div>

        <footer className="qsearch__foot">
          <p className="label qsearch__legend">
            ↑ ↓ MOVE · ENTER LAUNCH · Y DETAIL · ESC CLOSE
          </p>
        </footer>
      </div>
    </div>
  );
}
