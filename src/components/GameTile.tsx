/**
 * GameTile — Editorial cover card.
 *
 * Editorial language:
 *   - No springs, no glass, no overshoot. The tile-focus animation
 *     in styles/animations.css is the only motion (1px → 2px border,
 *     scale 1.0 → 1.04, 200 ms ease-in-out).
 *   - Source label uses .label primitive (small-caps, tracked, dim).
 *   - Single accent (#C5402F) is reserved for the ▶ PLAY button on
 *     the GameDetailPage; tiles use only neutrals + focus ring.
 */

import { useState } from 'react';
import { type AppEntry, type GameEntry, imageUrl } from '../api/bridge';
import './GameTile.css';

interface Props {
  game: GameEntry;
  size?: 'normal' | 'large' | 'landscape';
  onSelect?: (game: GameEntry) => void;
  onFavorite?: (game: GameEntry) => void;
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

export function GameTile({
  game,
  size = 'normal',
  onSelect,
  onFavorite,
}: Props) {
  const [imgLoaded, setImgLoaded] = useState(false);

  const artSrc = imageUrl(game.art_url);
  const sourceLabel = SOURCE_LABELS[game.source] ?? game.source.toUpperCase();

  return (
    <div
      className={`game-tile game-tile--${size} tile-focus ${
        !game.is_installed ? 'game-tile--uninstalled' : ''
      }`}
      data-focusable
      tabIndex={0}
      onClick={() => onSelect?.(game)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect?.(game);
        }
        if (e.key === 'y' || e.key === 'Y') {
          e.preventDefault();
          onFavorite?.(game);
        }
      }}
      role="button"
      aria-label={`${game.name} — ${sourceLabel}`}
    >
      <div className="game-tile__art">
        {artSrc !== '' && (
          <img
            src={artSrc}
            alt=""
            aria-hidden="true"
            loading="lazy"
            onLoad={() => setImgLoaded(true)}
            className={`game-tile__img ${imgLoaded ? 'game-tile__img--loaded' : ''}`}
          />
        )}
        {!imgLoaded && (
          <div className="game-tile__placeholder" aria-hidden="true" />
        )}
      </div>

      <div className="game-tile__caption">
        <p className="game-tile__source label">{sourceLabel}</p>
        <h3 className="game-tile__name">{game.name}</h3>
        {game.playtime_display !== '' && (
          <p className="game-tile__playtime">{game.playtime_display}</p>
        )}
      </div>

      {game.is_favorite && (
        <span
          className="game-tile__favorite-mark"
          aria-label="Favorite"
          title="Favorite"
        >
          ♥
        </span>
      )}

      {!game.is_installed && (
        <span className="game-tile__not-installed label">NOT INSTALLED</span>
      )}
    </div>
  );
}
