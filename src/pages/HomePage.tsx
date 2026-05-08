/**
 * HomePage — Editorial library grid.
 *
 * Continue Playing band on top (when there's recent activity), then a
 * single grid of every game. Reads the library from `useLibrary()` —
 * the provider does the actual fetch + retry once at the app root.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GameTile } from '../components/GameTile';
import { SearchBar } from '../components/SearchBar';
import { ScanProgress } from '../components/ScanProgress';
import { HomeGreeting } from '../components/HomeGreeting';
import { useLibrary } from '../api/LibraryContext';
import { useToast } from '../api/ToastContext';
import { useUiPrefs } from '../api/UiPrefsContext';
import { imageUrl, type AppEntry } from '../api/bridge';
import './HomePage.css';

/**
 * Best-effort timestamp for the "Recently Added" rail. The current
 * backend doesn't write a dedicated field, so we look for either
 * convention defensively. Falls back to last_played, then 0.
 */
function addedAt(g: AppEntry): number {
  const m = g.metadata;
  const candidates = [m.added_at, m.mtime, m.modified, m.created_at];
  for (const c of candidates) {
    if (typeof c === 'number' && Number.isFinite(c)) return c;
  }
  return g.last_played;
}

type SortMode = 'az' | 'recent';

export function HomePage() {
  const {
    games,
    status,
    error,
    refresh,
    isAutoScanning,
    scanProviders,
  } = useLibrary();
  const { toast } = useToast();
  const prefs = useUiPrefs();
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortMode>('az');
  const navigate = useNavigate();
  const lastToastedError = useRef<string>('');
  const gridRef = useRef<HTMLDivElement | null>(null);

  // Surface load failures as a transient toast in addition to the inline
  // retry surface — guards against the user navigating away mid-error
  // and missing the embedded message.
  useEffect(() => {
    if (status === 'error' && error !== '' && error !== lastToastedError.current) {
      toast(`Library load failed: ${error}`, 'error');
      lastToastedError.current = error;
    }
    if (status === 'ready') {
      lastToastedError.current = '';
    }
  }, [status, error, toast]);

  const recentlyPlayed = useMemo(
    () =>
      games
        .filter((g) => g.is_game && g.last_played > 0)
        .sort((a, b) => b.last_played - a.last_played)
        .slice(0, 8),
    [games],
  );

  // Recently Added: top 8 by added_at signal. Requires ≥3 entries with
  // a real timestamp — otherwise the rail collapses to "first 8 by
  // last_played" which duplicates Continue Playing.
  const recentlyAdded = useMemo(() => {
    if (!prefs.recentlyAddedEnabled) return [] as AppEntry[];
    const onlyGames = games.filter((g) => g.is_game);
    const withSignal = onlyGames.filter((g) => addedAt(g) > 0);
    if (withSignal.length < 3) return [] as AppEntry[];
    const playedIds = new Set(recentlyPlayed.map((g) => g.id));
    return withSignal
      .filter((g) => !playedIds.has(g.id))
      .sort((a, b) => {
        const da = addedAt(a);
        const db = addedAt(b);
        if (da !== db) return db - da;
        return a.name.localeCompare(b.name);
      })
      .slice(0, 8);
  }, [games, recentlyPlayed, prefs.recentlyAddedEnabled]);

  const filtered = useMemo(() => {
    let list = games.filter((g) => g.is_game);
    if (search !== '') {
      const q = search.toLowerCase();
      list = list.filter((g) => g.name.toLowerCase().includes(q));
    }
    list = list.slice().sort((a, b) => {
      if (a.is_favorite !== b.is_favorite) return a.is_favorite ? -1 : 1;
      if (sort === 'recent') return b.last_played - a.last_played;
      return a.name.localeCompare(b.name);
    });
    return list;
  }, [games, search, sort]);

  const onOpen = useCallback(
    (g: AppEntry): void => {
      navigate(`/game/${encodeURIComponent(g.id)}`);
    },
    [navigate],
  );

  // "Explore your library" CTA: scroll to the grid + focus the first
  // tile so a controller user can act immediately.
  const onExplore = useCallback(() => {
    const grid = gridRef.current;
    if (grid !== null) {
      grid.scrollIntoView({ behavior: 'smooth', block: 'start' });
      window.requestAnimationFrame(() => {
        const first = grid.querySelector<HTMLElement>('[data-focusable]');
        first?.focus();
      });
    }
  }, []);

  // "Surprise me": pick a random installed game from the current
  // filtered list and route to its detail page (no auto-launch — the
  // user still gets to confirm via ▶ PLAY).
  const onSurprise = useCallback(() => {
    const pool = filtered.filter((g) => g.is_installed);
    const candidates = pool.length > 0 ? pool : filtered;
    if (candidates.length === 0) return;
    const pick = candidates[Math.floor(Math.random() * candidates.length)];
    if (pick === undefined) return;
    toast(`Surprise: ${pick.name}`, 'info');
    onOpen(pick);
  }, [filtered, onOpen, toast]);

  // ── Ambient hero ──────────────────────────────────────────────────
  // The page background gets a heavily-blurred copy of whichever game
  // is currently in focus (or, on first paint, the first carousel /
  // grid item). We swap between two CSS layers (--ambient-art-a /
  // --ambient-art-b) so the change crossfades for 400 ms — matching
  // the hero-art idle behaviour of Steam Big Picture.
  const ambientLayer = useRef<'a' | 'b'>('a');
  const ambientUrlRef = useRef<string>('');
  const defaultAmbient = useMemo(() => {
    const pick = recentlyPlayed[0] ?? filtered[0];
    return pick !== undefined ? imageUrl(pick.art_url) : '';
  }, [recentlyPlayed, filtered]);

  useEffect(() => {
    const body = document.body;
    body.classList.add('home-ambient');
    if (defaultAmbient !== '' && defaultAmbient !== ambientUrlRef.current) {
      body.style.setProperty('--ambient-art-a', `url("${defaultAmbient}")`);
      body.style.setProperty('--ambient-a-opacity', '1');
      body.style.setProperty('--ambient-b-opacity', '0');
      ambientUrlRef.current = defaultAmbient;
      ambientLayer.current = 'a';
    }
    return () => {
      body.classList.remove('home-ambient');
      body.style.removeProperty('--ambient-art-a');
      body.style.removeProperty('--ambient-art-b');
      body.style.removeProperty('--ambient-a-opacity');
      body.style.removeProperty('--ambient-b-opacity');
      ambientUrlRef.current = '';
    };
  }, [defaultAmbient]);

  // Update ambient when the user moves focus over a tile (mouse hover
  // or D-pad). One document-level listener feeds both the carousel and
  // the main grid — each tile doesn't need to know about ambient art.
  useEffect(() => {
    const onFocusIn = (e: FocusEvent): void => {
      const target = e.target;
      if (!(target instanceof HTMLElement)) return;
      const tile = target.closest('.game-tile');
      if (tile === null) return;
      const img = tile.querySelector('img');
      const src = img?.getAttribute('src') ?? '';
      if (src === '' || src === ambientUrlRef.current) return;

      const body = document.body;
      const next = ambientLayer.current === 'a' ? 'b' : 'a';
      body.style.setProperty(`--ambient-art-${next}`, `url("${src}")`);
      body.style.setProperty(`--ambient-${next}-opacity`, '1');
      body.style.setProperty(
        `--ambient-${ambientLayer.current}-opacity`,
        '0',
      );
      ambientLayer.current = next;
      ambientUrlRef.current = src;
    };
    document.addEventListener('focusin', onFocusIn);
    return () => document.removeEventListener('focusin', onFocusIn);
  }, []);

  const onlyGames = useMemo(() => games.filter((g) => g.is_game), [games]);
  const showRecent = recentlyPlayed.length > 0;
  const showRecentlyAdded =
    prefs.recentlyAddedEnabled && recentlyAdded.length > 0;
  const showExploreCta = !showRecent && onlyGames.length > 0;

  return (
    <div className="home fade-in">
      {prefs.greetingEnabled && (
        <HomeGreeting
          name={prefs.displayName}
          weatherEnabled={prefs.weatherEnabled}
          latitude={prefs.weatherLatitude}
          longitude={prefs.weatherLongitude}
        />
      )}

      {showRecent ? (
        <section className="home__section">
          <p className="label home__section-head">CONTINUE PLAYING</p>
          <div className="home__carousel">
            {recentlyPlayed.map((game) => (
              <GameTile
                key={game.id}
                game={game}
                size="landscape"
                onSelect={onOpen}
              />
            ))}
          </div>
          <hr className="rule" />
        </section>
      ) : showExploreCta ? (
        <section className="home__section home__section--cta">
          <p className="label home__section-head">START HERE</p>
          <div className="home__cta">
            <p className="home__cta-title">Explore your library.</p>
            <p className="home__cta-body">
              Pixiis found {onlyGames.length}{' '}
              {onlyGames.length === 1 ? 'game' : 'games'} — pick one to begin.
            </p>
            <button
              type="button"
              className="home__retry"
              onClick={onExplore}
              data-focusable
            >
              Browse
            </button>
          </div>
          <hr className="rule" />
        </section>
      ) : null}

      {showRecentlyAdded && (
        <section className="home__section">
          <p className="label home__section-head">RECENTLY ADDED</p>
          <div className="home__carousel">
            {recentlyAdded.map((game) => (
              <GameTile
                key={game.id}
                game={game}
                size="landscape"
                onSelect={onOpen}
              />
            ))}
          </div>
          <hr className="rule" />
        </section>
      )}

      <section className="home__section">
        {/* Top hairline only when no rail (or CTA) drew its own. */}
        {!showRecent && !showRecentlyAdded && !showExploreCta && (
          <hr className="rule home__top-rule" />
        )}
        <header className="home__toolbar">
          <p className="label home__section-head">LIBRARY</p>
          <SearchBar value={search} onChange={setSearch} />
          <div className="home__pills">
            <button
              className={`home__pill ${sort === 'az' ? 'home__pill--active' : ''}`}
              onClick={() => setSort('az')}
              data-focusable
              aria-pressed={sort === 'az'}
            >
              A–Z
            </button>
            <button
              className={`home__pill ${sort === 'recent' ? 'home__pill--active' : ''}`}
              onClick={() => setSort('recent')}
              data-focusable
              aria-pressed={sort === 'recent'}
            >
              Recent
            </button>
          </div>
          {prefs.surpriseMeEnabled && filtered.length > 0 && (
            <button
              className="home__pill home__pill--surprise"
              onClick={onSurprise}
              data-focusable
              title="Pick a random game from your library"
              aria-label="Surprise me — pick a random game"
            >
              Surprise me
            </button>
          )}
          <span className="home__count">
            {filtered.length} {filtered.length === 1 ? 'game' : 'games'}
          </span>
        </header>

        {status === 'error' ? (
          <div className="home__empty" role="alert">
            <p className="home__empty-title">Failed to load library</p>
            <p className="home__empty-body">{error}</p>
            <button
              className="home__retry"
              onClick={refresh}
              data-focusable
            >
              Retry
            </button>
          </div>
        ) : isAutoScanning ? (
          // First-launch auto-scan: surface the same magazine-style
          // per-provider readout Onboarding shows so the window doesn't
          // look frozen during the 5–30 s discovery sweep.
          <div className="home__empty home__empty--scanning">
            <p className="home__empty-title">Discovering your library…</p>
            <p className="home__empty-body">
              Pixiis is sweeping your stores and common game folders. This
              usually takes a few seconds.
            </p>
            <ScanProgress rows={scanProviders} scanning />
          </div>
        ) : status === 'loading' && games.length === 0 ? (
          <div className="home__empty">
            <p className="home__empty-title">One moment.</p>
            <p className="label">LOADING LIBRARY</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="home__empty">
            <p className="home__empty-title">
              {search !== '' ? 'No matches' : 'No games yet'}
            </p>
            {search === '' ? (
              <p className="home__empty-body">
                Pixiis scans Steam and your common game folders on launch.
                Click <em>Scan Library</em> from the tray, or add an extra
                folder under Settings → Library.
              </p>
            ) : (
              <button
                className="home__retry"
                onClick={() => setSearch('')}
                data-focusable
              >
                Clear search
              </button>
            )}
          </div>
        ) : (
          <div className="home__grid" ref={gridRef}>
            {filtered.map((game) => (
              <GameTile key={game.id} game={game} onSelect={onOpen} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
