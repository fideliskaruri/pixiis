/**
 * GameDetailPage — Editorial detail view for a single game.
 *
 * Loads the entry by id from the library cache (the same `getLibrary()`
 * call that fed the home grid). Hero art, serif game name, source label,
 * playtime, ▶ PLAY accent button, favorite toggle, and a back link.
 *
 * RAWG description / screenshots / trailer are deliberately deferred to
 * the next iteration — this page proves the route + types + accent-only
 * editorial loop end-to-end.
 */

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getLibrary,
  imageUrl,
  launchGame,
  toggleFavorite,
  type AppEntry,
} from '../api/bridge';
import './GameDetailPage.css';

type LaunchState = 'idle' | 'launching' | 'launched' | 'error';

const SOURCE_LABELS: Record<AppEntry['source'], string> = {
  steam: 'STEAM',
  xbox: 'XBOX',
  epic: 'EPIC',
  gog: 'GOG',
  ea: 'EA',
  startmenu: 'PC',
  manual: 'CUSTOM',
};

export function GameDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [game, setGame] = useState<AppEntry | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [favorite, setFavorite] = useState(false);
  const [launchState, setLaunchState] = useState<LaunchState>('idle');
  const [launchError, setLaunchError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    getLibrary()
      .then((entries) => {
        if (cancelled) return;
        const match = entries.find((e) => e.id === id) ?? null;
        if (match === null) {
          setNotFound(true);
          return;
        }
        setGame(match);
        setFavorite(match.is_favorite);
      })
      .catch(() => {
        if (!cancelled) setNotFound(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const onPlay = async (): Promise<void> => {
    if (game === null || launchState === 'launching') return;
    setLaunchState('launching');
    setLaunchError('');
    try {
      await launchGame(game.id);
      setLaunchState('launched');
      // Reset the button after a short visual confirmation so a second
      // click re-launches if the user wants it.
      window.setTimeout(() => setLaunchState('idle'), 1500);
    } catch (err) {
      setLaunchError(err instanceof Error ? err.message : String(err));
      setLaunchState('error');
    }
  };

  const onToggleFavorite = async (): Promise<void> => {
    if (game === null) return;
    try {
      const next = await toggleFavorite(game.id);
      setFavorite(next);
    } catch {
      /* surface errors here in a future iteration */
    }
  };

  if (notFound) {
    return (
      <div className="detail detail--empty">
        <p className="text-h3 text-secondary">Game not found</p>
        <button className="detail__back" onClick={() => navigate(-1)}>
          ← Back
        </button>
      </div>
    );
  }

  if (game === null) {
    return (
      <div className="detail detail--empty">
        <p className="label">LOADING…</p>
      </div>
    );
  }

  const art = imageUrl(game.art_url);
  const sourceLabel = SOURCE_LABELS[game.source] ?? game.source.toUpperCase();
  const playButtonLabel =
    launchState === 'launching'
      ? 'LAUNCHING…'
      : launchState === 'launched'
        ? 'LAUNCHED ✓'
        : '▶ PLAY';

  return (
    <article className="detail fade-in">
      <button
        className="detail__back"
        onClick={() => navigate(-1)}
        data-focusable
        aria-label="Back to library"
      >
        ← Back
      </button>

      <div className="detail__hero">
        {art !== '' && (
          <img
            className="detail__art"
            src={art}
            alt=""
            // alt is decorative — the real title lives in the heading below
            aria-hidden="true"
          />
        )}
        <div className="detail__hero-fade" aria-hidden="true" />
      </div>

      <header className="detail__header">
        <p className="label">{sourceLabel}</p>
        <h1 className="detail__title display">{game.name}</h1>

        <dl className="detail__meta">
          {game.playtime_display !== '' && (
            <div className="detail__meta-row">
              <dt className="label">PLAYED</dt>
              <dd className="text-body">{game.playtime_display}</dd>
            </div>
          )}
          {!game.is_installed && (
            <div className="detail__meta-row">
              <dt className="label">STATUS</dt>
              <dd className="text-body text-muted">Not installed</dd>
            </div>
          )}
        </dl>
      </header>

      <div className="detail__actions">
        <button
          className="accent-btn detail__play"
          onClick={onPlay}
          disabled={!game.is_installed || launchState === 'launching'}
          data-focusable
        >
          {playButtonLabel}
        </button>

        <button
          className="detail__favorite"
          onClick={onToggleFavorite}
          aria-pressed={favorite}
          aria-label={favorite ? 'Remove from favorites' : 'Add to favorites'}
          data-focusable
        >
          {favorite ? '♥ Favorited' : '♡ Favorite'}
        </button>
      </div>

      {launchError !== '' && (
        <p className="detail__error text-body" role="alert">
          {launchError}
        </p>
      )}
    </article>
  );
}
