/**
 * GameDetailPage — Editorial detail view for a single game.
 *
 * Loads the entry by id from the same library cache (`getLibrary()`)
 * that fed the home grid. Hero art, serif game name, source label,
 * playtime, ▶ PLAY accent button, favorite toggle, back link.
 *
 * RAWG description / screenshots / trailer are deferred to a later
 * iteration — this page proves the route + types + accent-only
 * editorial loop end-to-end.
 */

import { useEffect, useRef, useState } from 'react';
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
type LoadState =
  | { kind: 'loading' }
  | { kind: 'loaded'; game: AppEntry }
  | { kind: 'not-found' }
  | { kind: 'error'; message: string };

const SOURCE_LABELS: Partial<Record<AppEntry['source'], string>> = {
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

  const [state, setState] = useState<LoadState>({ kind: 'loading' });
  const [favorite, setFavorite] = useState(false);
  const [favoriteError, setFavoriteError] = useState('');
  const [launchState, setLaunchState] = useState<LaunchState>('idle');
  const [launchError, setLaunchError] = useState('');

  // setTimeout handle for the post-launch visual confirmation —
  // cleared on unmount and on every re-arm.
  const launchedTimer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLibrary()
      .then((entries) => {
        if (cancelled) return;
        const match = entries.find((e) => e.id === id);
        if (match === undefined) {
          setState({ kind: 'not-found' });
          return;
        }
        setState({ kind: 'loaded', game: match });
        setFavorite(match.is_favorite);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({
          kind: 'error',
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Tear the LAUNCHED timer down with the component.
  useEffect(() => {
    return () => {
      if (launchedTimer.current !== null) {
        window.clearTimeout(launchedTimer.current);
        launchedTimer.current = null;
      }
    };
  }, []);

  const onPlay = async (): Promise<void> => {
    if (state.kind !== 'loaded' || launchState === 'launching') return;
    setLaunchState('launching');
    setLaunchError('');
    try {
      await launchGame(state.game.id);
      setLaunchState('launched');
      if (launchedTimer.current !== null) {
        window.clearTimeout(launchedTimer.current);
      }
      launchedTimer.current = window.setTimeout(() => {
        setLaunchState('idle');
        launchedTimer.current = null;
      }, 1500);
    } catch (err: unknown) {
      setLaunchError(err instanceof Error ? err.message : String(err));
      setLaunchState('error');
    }
  };

  const onToggleFavorite = async (): Promise<void> => {
    if (state.kind !== 'loaded') return;
    setFavoriteError('');
    try {
      const next = await toggleFavorite(state.game.id);
      setFavorite(next);
    } catch (err: unknown) {
      setFavoriteError(err instanceof Error ? err.message : String(err));
    }
  };

  if (state.kind === 'loading') {
    return (
      <div className="detail detail--empty fade-in">
        <p className="label">LOADING…</p>
      </div>
    );
  }

  if (state.kind === 'not-found') {
    return (
      <div className="detail detail--empty fade-in">
        <p className="label">NOT FOUND</p>
        <p className="detail__empty-body">No library entry with id <code>{id}</code>.</p>
        <button
          className="detail__back"
          onClick={() => navigate(-1)}
          data-focusable
        >
          ← Back
        </button>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className="detail detail--empty fade-in">
        <p className="label">FAILED TO LOAD</p>
        <p className="detail__empty-body">{state.message}</p>
        <button
          className="detail__back"
          onClick={() => navigate(-1)}
          data-focusable
        >
          ← Back
        </button>
      </div>
    );
  }

  const game = state.game;
  const art = imageUrl(game.art_url);
  const sourceLabel = SOURCE_LABELS[game.source] ?? game.source.toUpperCase();
  const playButtonLabel =
    launchState === 'launching'
      ? 'LAUNCHING…'
      : launchState === 'launched'
        ? 'LAUNCHED'
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
              <dd className="detail__meta-value">{game.playtime_display}</dd>
            </div>
          )}
          {!game.is_installed && (
            <div className="detail__meta-row">
              <dt className="label">STATUS</dt>
              <dd className="detail__meta-value detail__meta-value--dim">Not installed</dd>
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
        <p className="detail__error" role="alert">
          {launchError}
        </p>
      )}
      {favoriteError !== '' && (
        <p className="detail__error" role="alert">
          {favoriteError}
        </p>
      )}
    </article>
  );
}
