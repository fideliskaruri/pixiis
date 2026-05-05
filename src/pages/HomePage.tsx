/**
 * HomePage — Recently played carousel + game grid.
 * PS5-inspired: horizontal "Continue Playing" row, then a grid of all games.
 */

import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { GameTile } from '../components/GameTile';
import { SearchBar } from '../components/SearchBar';
import { getLibrary, type GameEntry } from '../api/bridge';
import './HomePage.css';

export function HomePage() {
  const [games, setGames] = useState<GameEntry[]>([]);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<'az' | 'recent'>('az');
  const navigate = useNavigate();

  useEffect(() => {
    getLibrary().then(setGames).catch(() => {});
  }, []);

  // Recently played (top carousel)
  const recentlyPlayed = useMemo(
    () => games
      .filter(g => g.is_game && g.last_played > 0)
      .sort((a, b) => b.last_played - a.last_played)
      .slice(0, 8),
    [games],
  );

  // Filtered + sorted game grid
  const filtered = useMemo(() => {
    let list = games.filter(g => g.is_game);
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(g => g.name.toLowerCase().includes(q));
    }
    // Favorites first, then sort
    list.sort((a, b) => {
      if (a.is_favorite !== b.is_favorite) return a.is_favorite ? -1 : 1;
      if (sort === 'recent') return b.last_played - a.last_played;
      return a.name.localeCompare(b.name);
    });
    return list;
  }, [games, search, sort]);

  const gameCount = filtered.length;

  return (
    <div className="home">
      {/* Recently Played Carousel */}
      {recentlyPlayed.length > 0 && (
        <section className="home__section">
          <h2 className="text-overline">Continue Playing</h2>
          <div className="home__carousel">
            {recentlyPlayed.map((game, i) => (
              <motion.div
                key={game.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <GameTile
                  game={game}
                  size="landscape"
                  onSelect={(g) => navigate(`/game/${g.id}`)}
                />
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {/* Search + Sort + Count */}
      <div className="home__toolbar">
        <SearchBar value={search} onChange={setSearch} />
        <div className="home__pills">
          <button
            className={`pill ${sort === 'az' ? 'pill--active' : ''}`}
            onClick={() => setSort('az')}
            data-focusable
          >
            A–Z
          </button>
          <button
            className={`pill ${sort === 'recent' ? 'pill--active' : ''}`}
            onClick={() => setSort('recent')}
            data-focusable
          >
            Recent
          </button>
        </div>
        <span className="home__count text-caption text-muted">{gameCount} games</span>
      </div>

      {/* Game Grid */}
      <div className="home__grid">
        {filtered.length === 0 ? (
          <div className="home__empty">
            <p className="text-h3 text-secondary">
              {search ? 'No matching games' : 'No games found'}
            </p>
            {!search && (
              <p className="text-body text-muted" style={{ marginTop: 8 }}>
                Go to Settings → Library to add your game sources.
              </p>
            )}
          </div>
        ) : (
          filtered.map((game, i) => (
            <motion.div
              key={game.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.02, duration: 0.3 }}
            >
              <GameTile
                game={game}
                onSelect={(g) => navigate(`/game/${g.id}`)}
              />
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
}
