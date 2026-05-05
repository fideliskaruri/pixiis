/**
 * GameDetailPage — Editorial detail view for a single game.
 *
 * Reads the entry from the library context (single fetch lives in
 * LibraryProvider). On mount, fires a background RAWG metadata lookup
 * and renders the description / screenshots / genres / Metacritic /
 * release date when they arrive — page is fully usable before then.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  imageUrl,
  launchGame,
  lookupRawg,
  toggleFavorite,
  type AppEntry,
  type RawgGameData,
} from '../api/bridge';
import { useLibrary } from '../api/LibraryContext';
import './GameDetailPage.css';

type LaunchState = 'idle' | 'launching' | 'launched' | 'error';

const SOURCE_LABELS: Partial<Record<AppEntry['source'], string>> = {
  steam: 'STEAM',
  xbox: 'XBOX',
  epic: 'EPIC',
  gog: 'GOG',
  ea: 'EA',
  startmenu: 'PC',
  manual: 'CUSTOM',
};

const MAX_SCREENSHOTS = 6;

export function GameDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { byId, status: libraryStatus, error: libraryError } = useLibrary();

  const game = byId(id);

  const [favorite, setFavorite] = useState<boolean>(game?.is_favorite ?? false);
  const [favoriteError, setFavoriteError] = useState('');
  const [launchState, setLaunchState] = useState<LaunchState>('idle');
  const [launchError, setLaunchError] = useState('');

  const [rawg, setRawg] = useState<RawgGameData | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null);

  const launchedTimer = useRef<number | null>(null);

  // Sync the favorite local state when the underlying entry changes.
  useEffect(() => {
    if (game !== undefined) setFavorite(game.is_favorite);
  }, [game]);

  // Background RAWG lookup. Failure is non-fatal — page renders without it.
  useEffect(() => {
    if (game === undefined) return;
    let cancelled = false;
    void lookupRawg(game.name).then((data) => {
      if (!cancelled) setRawg(data);
    });
    return () => {
      cancelled = true;
    };
  }, [game]);

  // Tear down the LAUNCHED-confirmation timer with the component.
  useEffect(() => {
    return () => {
      if (launchedTimer.current !== null) {
        window.clearTimeout(launchedTimer.current);
        launchedTimer.current = null;
      }
    };
  }, []);

  // Esc closes the screenshot lightbox.
  useEffect(() => {
    if (lightbox === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightbox(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightbox]);

  const onPlay = async (): Promise<void> => {
    if (game === undefined || launchState === 'launching') return;
    setLaunchState('launching');
    setLaunchError('');
    try {
      await launchGame(game.id);
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
    if (game === undefined) return;
    setFavoriteError('');
    try {
      const next = await toggleFavorite(game.id);
      setFavorite(next);
    } catch (err: unknown) {
      setFavoriteError(err instanceof Error ? err.message : String(err));
    }
  };

  if (libraryStatus === 'error') {
    return (
      <div className="detail detail--empty fade-in">
        <p className="label">FAILED TO LOAD LIBRARY</p>
        <p className="detail__empty-body">{libraryError}</p>
        <button className="detail__back" onClick={() => navigate(-1)} data-focusable>
          ← Back
        </button>
      </div>
    );
  }

  if (game === undefined) {
    if (libraryStatus === 'loading' || libraryStatus === 'idle') {
      return (
        <div className="detail detail--empty fade-in">
          <p className="label">LOADING…</p>
        </div>
      );
    }
    return (
      <div className="detail detail--empty fade-in">
        <p className="label">NOT FOUND</p>
        <p className="detail__empty-body">
          No library entry with id <code>{id}</code>.
        </p>
        <button className="detail__back" onClick={() => navigate(-1)} data-focusable>
          ← Back
        </button>
      </div>
    );
  }

  const art = imageUrl(game.art_url);
  const sourceLabel = SOURCE_LABELS[game.source] ?? game.source.toUpperCase();
  const playButtonLabel =
    launchState === 'launching'
      ? 'LAUNCHING…'
      : launchState === 'launched'
        ? 'LAUNCHED'
        : '▶ PLAY';

  // RAWG description prefers the rich `description` field; fall back gracefully.
  const description = rawg?.description ?? '';
  const genres = rawg?.genres ?? [];
  const screenshots = (rawg?.screenshots ?? []).slice(0, MAX_SCREENSHOTS);
  const metacritic = rawg?.metacritic ?? 0;
  const released = rawg?.released ?? '';

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
        {art !== '' && <img className="detail__art" src={art} alt="" />}
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
          {metacritic > 0 && (
            <div className="detail__meta-row">
              <dt className="label">METACRITIC</dt>
              <dd className="detail__meta-value">{metacritic}</dd>
            </div>
          )}
          {released !== '' && (
            <div className="detail__meta-row">
              <dt className="label">RELEASED</dt>
              <dd className="detail__meta-value">{released}</dd>
            </div>
          )}
          {!game.is_installed && (
            <div className="detail__meta-row">
              <dt className="label">STATUS</dt>
              <dd className="detail__meta-value detail__meta-value--dim">
                Not installed
              </dd>
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

      {description !== '' && (
        <section className="detail__about">
          <p className="label">ABOUT</p>
          <p className="detail__description">{description}</p>
          {genres.length > 0 && (
            <ul className="detail__genres" aria-label="Genres">
              {genres.map((g) => (
                <li key={g} className="detail__genre label">
                  {g.toUpperCase()}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {screenshots.length > 0 && (
        <section className="detail__screens">
          <p className="label">SCREENSHOTS</p>
          <div className="detail__screens-grid">
            {screenshots.map((src) => (
              <button
                key={src}
                className="detail__screen"
                onClick={() => setLightbox(src)}
                data-focusable
                aria-label="Open screenshot"
              >
                <img src={src} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </section>
      )}

      {lightbox !== null && (
        <div
          className="detail__lightbox"
          role="dialog"
          aria-modal="true"
          onClick={() => setLightbox(null)}
        >
          <img src={lightbox} alt="" className="detail__lightbox-img" />
        </div>
      )}
    </article>
  );
}
