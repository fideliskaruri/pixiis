/**
 * HomePage — Editorial library grid.
 *
 * Continue Playing band on top (when there's recent activity), then a
 * single grid of every game. Reads the library from `useLibrary()` —
 * the provider does the actual fetch + retry once at the app root.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GameTile } from '../components/GameTile';
import { SearchBar } from '../components/SearchBar';
import { useLibrary } from '../api/LibraryContext';
import { useToast } from '../api/ToastContext';
import type { AppEntry } from '../api/bridge';
import './HomePage.css';

type SortMode = 'az' | 'recent';

export function HomePage() {
  const { games, status, error, refresh } = useLibrary();
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortMode>('az');
  const navigate = useNavigate();
  const lastToastedError = useRef<string>('');

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

  const onOpen = (g: AppEntry): void => {
    navigate(`/game/${encodeURIComponent(g.id)}`);
  };

  return (
    <div className="home fade-in">
      {recentlyPlayed.length > 0 && (
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
      )}

      <section className="home__section">
        {/* Top hairline only when Continue Playing didn't render its own. */}
        {recentlyPlayed.length === 0 && <hr className="rule home__top-rule" />}
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
            {search === '' && (
              <p className="home__empty-body">
                Pixiis scans Steam and your common game folders on launch.
                Click <em>Scan Library</em> from the tray, or add an extra
                folder under Settings → Library.
              </p>
            )}
          </div>
        ) : (
          <div className="home__grid">
            {filtered.map((game) => (
              <GameTile key={game.id} game={game} onSelect={onOpen} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
