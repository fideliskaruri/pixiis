/**
 * HomePage — Editorial library grid.
 *
 * Continue Playing band on top (when there's recent activity), then a
 * single grid of every game. Section headers use the .label primitive
 * (small-caps tracked Inter), rules separate sections, no framer-motion
 * springs. Sort + filter live in a quiet toolbar.
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GameTile } from '../components/GameTile';
import { SearchBar } from '../components/SearchBar';
import { getLibrary, type AppEntry } from '../api/bridge';
import './HomePage.css';

type SortMode = 'az' | 'recent';

export function HomePage() {
  const [games, setGames] = useState<AppEntry[]>([]);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortMode>('az');
  const [loadError, setLoadError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    setLoadError('');
    getLibrary()
      .then((entries) => {
        if (!cancelled) setGames(entries);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

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

        {loadError !== '' ? (
          <div className="home__empty" role="alert">
            <p className="display home__empty-title">Failed to load library</p>
            <p className="home__empty-body">{loadError}</p>
            <button
              className="home__retry"
              onClick={() => setReloadKey((n) => n + 1)}
              data-focusable
            >
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="home__empty">
            <p className="display home__empty-title">
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
