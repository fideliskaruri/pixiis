/**
 * GameTile — The hero element. A floating glass card with cover art.
 *
 * PS5-inspired: on focus, the card rises toward you with a spring
 * animation, casts a warm coral shadow, and the art brightens.
 * Everything else dims.
 */

import { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { type GameEntry, imageUrl } from '../api/bridge';
import './GameTile.css';

interface Props {
  game: GameEntry;
  size?: 'normal' | 'large' | 'landscape';
  onSelect?: (game: GameEntry) => void;
  onFavorite?: (game: GameEntry) => void;
}

const SOURCE_LABELS: Record<string, string> = {
  steam: 'STEAM',
  xbox: 'XBOX',
  epic: 'EPIC',
  gog: 'GOG',
  ea: 'EA',
  startmenu: 'PC',
  manual: 'CUSTOM',
};

export function GameTile({ game, size = 'normal', onSelect, onFavorite }: Props) {
  const [focused, setFocused] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const artSrc = imageUrl(game.art_url);
  const sourceLabel = SOURCE_LABELS[game.source] || game.source.toUpperCase();

  return (
    <motion.div
      ref={ref}
      className={`game-tile game-tile--${size} ${focused ? 'game-tile--focused' : ''} ${!game.is_installed ? 'game-tile--uninstalled' : ''}`}
      data-focusable
      tabIndex={0}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onClick={() => onSelect?.(game)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') onSelect?.(game);
        if (e.key === 'y' || e.key === 'Y') onFavorite?.(game);
      }}
      whileHover={{ scale: 1.03, y: -4 }}
      whileFocus={{ scale: 1.05, y: -8 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      layout
    >
      {/* Cover art */}
      <div className="game-tile__art">
        {artSrc && (
          <img
            src={artSrc}
            alt={game.name}
            loading="lazy"
            onLoad={() => setImgLoaded(true)}
            className={`game-tile__img ${imgLoaded ? 'game-tile__img--loaded' : ''}`}
          />
        )}
        {!imgLoaded && (
          <div className="game-tile__placeholder">
            <span className="game-tile__placeholder-icon">🎮</span>
          </div>
        )}
      </div>

      {/* Bottom gradient overlay */}
      <div className="game-tile__gradient" />

      {/* Source badge */}
      <span className="game-tile__badge">{sourceLabel}</span>

      {/* Favorite heart */}
      {game.is_favorite && (
        <button
          className="game-tile__heart game-tile__heart--active"
          onClick={(e) => { e.stopPropagation(); onFavorite?.(game); }}
          aria-label="Remove from favorites"
        >
          ♥
        </button>
      )}

      {/* Not installed overlay */}
      {!game.is_installed && (
        <div className="game-tile__uninstalled-badge">NOT INSTALLED</div>
      )}

      {/* Game name + playtime */}
      <div className="game-tile__info">
        <h3 className="game-tile__name">{game.name}</h3>
        {game.playtime_display && (
          <span className="game-tile__playtime">{game.playtime_display}</span>
        )}
      </div>
    </motion.div>
  );
}
