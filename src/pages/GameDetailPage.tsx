/**
 * GameDetailPage — Editorial detail view for a single game.
 *
 * Reads the entry from the library context (single fetch lives in
 * LibraryProvider). On mount, fires three background lookups in
 * parallel:
 *   - RAWG metadata (description / screenshots / genres / Metacritic).
 *   - YouTube top trailer (rendered as a nocookie iframe embed).
 *   - Twitch top live streams for the game's category.
 * Each section renders only when its lookup returns content, so the
 * page is fully usable before any of them resolve. When BOTH the
 * trailer AND streams come back empty (e.g. the user hasn't saved a
 * YouTube / Twitch credential in Settings yet) we surface a quiet
 * hint pointing them at Settings.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getTwitchStreams,
  getYouTubeTrailer,
  imageUrl,
  launchGame,
  lookupRawg,
  stopGame,
  toggleFavorite,
  useRunningGames,
  type AppEntry,
  type RawgGameData,
  type TwitchStream,
  type YouTubeTrailer,
} from '../api/bridge';
import { useLibrary } from '../api/LibraryContext';
import { useToast } from '../api/ToastContext';
import { useAutoFocus } from '../hooks/useAutoFocus';
import './GameDetailPage.css';

type LaunchState = 'idle' | 'launching' | 'launched' | 'stopping' | 'error';

const SOURCE_LABELS: Partial<Record<AppEntry['source'], string>> = {
  steam: 'STEAM',
  xbox: 'XBOX',
  epic: 'EPIC',
  gog: 'GOG',
  ea: 'EA',
  startmenu: 'PC',
  manual: 'CUSTOM',
  folder: 'PC',
};

const MAX_SCREENSHOTS = 6;

export function GameDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { byId, status: libraryStatus, error: libraryError } = useLibrary();
  const { toast } = useToast();
  const running = useRunningGames();
  const isRunning = running.some((r) => r.id === id);

  const game = byId(id);

  const [favorite, setFavorite] = useState<boolean>(game?.is_favorite ?? false);
  const [favoriteError, setFavoriteError] = useState('');
  const [launchState, setLaunchState] = useState<LaunchState>('idle');
  const [launchError, setLaunchError] = useState('');

  const [rawg, setRawg] = useState<RawgGameData | null>(null);
  const [trailer, setTrailer] = useState<YouTubeTrailer | null>(null);
  const [streams, setStreams] = useState<TwitchStream[]>([]);
  const [mediaProbed, setMediaProbed] = useState<boolean>(false);
  const [lightbox, setLightbox] = useState<string | null>(null);

  const launchedTimer = useRef<number | null>(null);

  // Sync the favorite local state when the underlying entry changes.
  useEffect(() => {
    if (game !== undefined) setFavorite(game.is_favorite);
  }, [game]);

  // Background RAWG lookup. Failure is non-fatal — page renders without it.
  // Keyed on `game?.id` so that local mutations to the entry (e.g. favorite
  // toggle re-deriving a fresh array reference in the library context)
  // don't fire a redundant network call.
  const gameId = game?.id;
  const gameName = game?.name;
  useEffect(() => {
    if (gameId === undefined || gameName === undefined) return;
    let cancelled = false;
    void lookupRawg(gameName).then((data) => {
      if (!cancelled) setRawg(data);
    });
    return () => {
      cancelled = true;
    };
  }, [gameId, gameName]);

  // Background YouTube trailer + Twitch live-streams lookup. Both fail
  // soft (null / empty) when the key isn't set — the empty-state hint
  // in the JSX nudges the user toward Settings if BOTH come back empty.
  // `mediaProbed` flips true once the first fetch settles so we don't
  // flash the empty-state hint while the page is still warming up.
  useEffect(() => {
    if (gameId === undefined || gameName === undefined) return;
    let cancelled = false;
    setMediaProbed(false);
    setTrailer(null);
    setStreams([]);
    const yt = getYouTubeTrailer(gameName).then((t) => {
      if (!cancelled) setTrailer(t);
    });
    const tw = getTwitchStreams(gameName).then((s) => {
      if (!cancelled) setStreams(s);
    });
    void Promise.allSettled([yt, tw]).then(() => {
      if (!cancelled) setMediaProbed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [gameId, gameName]);

  // Tear down the LAUNCHED-confirmation timer with the component.
  useEffect(() => {
    return () => {
      if (launchedTimer.current !== null) {
        window.clearTimeout(launchedTimer.current);
        launchedTimer.current = null;
      }
    };
  }, []);

  // Auto-focus the PLAY button on mount so a controller user can press
  // A immediately. Re-runs when the route's id changes (back-and-forth
  // between detail pages) so the button is always pre-focused on
  // re-entry. Falls back to the back button if the page is in a
  // not-found / error state and PLAY isn't rendered.
  useAutoFocus('.detail__play, .detail__back', [id]);


  const onPlay = async (): Promise<void> => {
    if (game === undefined || launchState === 'launching') return;
    setLaunchState('launching');
    setLaunchError('');
    try {
      await launchGame(game.id);
      setLaunchState('launched');
      toast(`Launching ${game.name}`, 'success');
      if (launchedTimer.current !== null) {
        window.clearTimeout(launchedTimer.current);
      }
      launchedTimer.current = window.setTimeout(() => {
        setLaunchState('idle');
        launchedTimer.current = null;
      }, 1500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setLaunchError(msg);
      setLaunchState('error');
      toast(`Failed to launch: ${msg}`, 'error');
    }
  };

  // Stop path mirrors `onPlay` but flips through the same state machine
  // so the button never double-fires. The running-game hook is the
  // source of truth for whether the game is actually running — once the
  // tracker prunes the row we'll fall back to the PLAY label.
  const onStop = async (): Promise<void> => {
    if (game === undefined || launchState === 'stopping') return;
    setLaunchState('stopping');
    setLaunchError('');
    try {
      await stopGame(game.id);
      toast(`Stopped ${game.name}`, 'success');
      // Don't snap to 'idle' here — the running-game event will flip
      // `isRunning` to false, which switches the button label back to
      // ▶ PLAY without us having to time it out.
      setLaunchState('idle');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setLaunchError(msg);
      setLaunchState('error');
      toast(`Failed to stop: ${msg}`, 'error');
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

  const sourceLabel = SOURCE_LABELS[game.source] ?? game.source.toUpperCase();
  // The PLAY button doubles as a STOP button while the game is live.
  // Steam-Big-Picture-style: one primary verb, no need to alt-tab.
  const playButtonLabel =
    launchState === 'launching'
      ? 'LAUNCHING…'
      : launchState === 'stopping'
        ? 'STOPPING…'
        : isRunning
          ? '■ STOP'
          : launchState === 'launched'
            ? 'LAUNCHED'
            : '▶ PLAY';
  const onPrimary = isRunning ? onStop : onPlay;
  const primaryDisabled =
    launchState === 'launching' ||
    launchState === 'stopping' ||
    (!isRunning && !game.is_installed);

  // RAWG description prefers the rich `description` field; fall back gracefully.
  const description = rawg?.description ?? '';
  const genres = rawg?.genres ?? [];
  const screenshots = (rawg?.screenshots ?? []).slice(0, MAX_SCREENSHOTS);
  const metacritic = rawg?.metacritic ?? 0;
  const released = rawg?.released ?? '';

  // Hero modes: a RAWG background_image is a wide banner art piece — render
  // it full-bleed with the title overlaid. Otherwise fall back to the
  // storefront's portrait poster (Steam library_600x900 etc.) and render
  // the title below; the wireframe's overlay only works on landscape art.
  const banner = rawg?.background_image ?? '';
  const heroMode: 'banner' | 'poster' =
    banner !== '' ? 'banner' : 'poster';
  const heroSrc =
    heroMode === 'banner' ? banner : imageUrl(game.art_url);

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

      <div className={`detail__hero detail__hero--${heroMode}`}>
        {heroSrc !== '' && (
          <img className="detail__art" src={heroSrc} alt="" />
        )}
        <div className="detail__hero-fade" aria-hidden="true" />
        {heroMode === 'banner' && (
          <div className="detail__hero-overlay">
            <p className="label">{sourceLabel}</p>
            <h1 className="detail__title display">{game.name}</h1>
          </div>
        )}
      </div>

      {heroMode === 'poster' && (
        <header className="detail__header">
          <p className="label">{sourceLabel}</p>
          <h1 className="detail__title display">{game.name}</h1>
        </header>
      )}

      <div className="detail__actions">
        <button
          className="accent-btn detail__play"
          onClick={() => {
            void onPrimary();
          }}
          disabled={primaryDisabled}
          data-focusable
          aria-label={isRunning ? `Stop ${game.name}` : `Play ${game.name}`}
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

      <div className="detail__body">
        <aside className="detail__sidebar" aria-label="Game details">
          <dl className="detail__meta">
            {game.playtime_display !== '' && (
              <div className="detail__meta-row">
                <dt className="label">PLAYED</dt>
                <dd className="detail__meta-value">{game.playtime_display}</dd>
              </div>
            )}
            {metacritic > 0 && (
              <div className="detail__meta-row">
                <dt className="label">RATING</dt>
                <dd className="detail__meta-value">{metacritic}</dd>
              </div>
            )}
            {released !== '' && (
              <div className="detail__meta-row">
                <dt className="label">RELEASED</dt>
                <dd className="detail__meta-value">{released}</dd>
              </div>
            )}
            <div className="detail__meta-row">
              <dt className="label">STORE</dt>
              <dd className="detail__meta-value">{sourceLabel}</dd>
            </div>
            {!game.is_installed && (
              <div className="detail__meta-row">
                <dt className="label">STATUS</dt>
                <dd className="detail__meta-value detail__meta-value--dim">
                  Not installed
                </dd>
              </div>
            )}
          </dl>

          {genres.length > 0 && (
            <div className="detail__sidebar-block">
              <p className="label">GENRE</p>
              <ul className="detail__genres" aria-label="Genres">
                {genres.map((g) => (
                  <li key={g} className="detail__genre label">
                    {g.toUpperCase()}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>

        <section className="detail__about" aria-labelledby="detail-about-head">
          <h2 id="detail-about-head" className="label">ABOUT</h2>
          {description !== '' ? (
            description.split(/\n{2,}/).map((para, i) => (
              <p key={i} className="detail__description">{para}</p>
            ))
          ) : (
            <p className="detail__description detail__description--dim">
              Description not available.
            </p>
          )}
        </section>
      </div>

      {trailer !== null && (
        <section className="detail__trailer" aria-labelledby="detail-trailer-head">
          <h2 id="detail-trailer-head" className="label">TRAILER</h2>
          <div className="detail__trailer-frame">
            <iframe
              src={`https://www.youtube-nocookie.com/embed/${trailer.video_id}?modestbranding=1&rel=0`}
              title={trailer.title}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              referrerPolicy="strict-origin-when-cross-origin"
            />
          </div>
        </section>
      )}

      {streams.length > 0 && (
        <section className="detail__streams" aria-labelledby="detail-streams-head">
          <h2 id="detail-streams-head" className="label">
            LIVE NOW · {streams.length}
          </h2>
          <ul className="detail__streams-list">
            {streams.map((s) => (
              <li key={s.user_name} className="detail__stream-card">
                <a
                  href={s.stream_url}
                  target="_blank"
                  rel="noreferrer"
                  data-focusable
                  aria-label={`Open ${s.user_name} on Twitch`}
                >
                  {s.thumbnail_url !== '' && (
                    <img
                      src={s.thumbnail_url
                        .replace('{width}', '320')
                        .replace('{height}', '180')}
                      alt=""
                      loading="lazy"
                      decoding="async"
                    />
                  )}
                  <div className="detail__stream-info">
                    <p className="display detail__stream-name">{s.user_name}</p>
                    <p className="label detail__stream-viewers">
                      {s.viewer_count.toLocaleString()} VIEWERS
                    </p>
                    <p className="detail__stream-title">{s.title}</p>
                  </div>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      {mediaProbed && trailer === null && streams.length === 0 && (
        <section className="detail__media-empty" aria-live="polite">
          <p className="label">NO TRAILER OR LIVE STREAMS</p>
          <p className="detail__media-empty-body">
            Add or check your YouTube and Twitch keys in Settings to surface trailers and live channels here.
          </p>
        </section>
      )}

      {screenshots.length > 0 && (
        <section className="detail__screens" aria-labelledby="detail-screens-head">
          <h2 id="detail-screens-head" className="label">SCREENSHOTS</h2>
          <div className="detail__screens-grid">
            {screenshots.map((src, i) => (
              <button
                key={`${i}-${src}`}
                className="detail__screen"
                onClick={() => setLightbox(src)}
                data-focusable
                aria-label="Open screenshot"
              >
                <img src={src} alt="" loading="lazy" decoding="async" />
              </button>
            ))}
          </div>
        </section>
      )}

      {lightbox !== null && (
        <Lightbox src={lightbox} onClose={() => setLightbox(null)} />
      )}
    </article>
  );
}

/**
 * Modal screenshot viewer with a minimal focus trap, esc-to-close,
 * and return-focus to the element that triggered it.
 */
function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<Element | null>(null);

  useEffect(() => {
    triggerRef.current = document.activeElement;
    dialogRef.current?.focus();
    return () => {
      const el = triggerRef.current;
      if (el instanceof HTMLElement) el.focus();
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'Tab') {
        // Single focusable element — keep tab focus inside the dialog.
        e.preventDefault();
        dialogRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      ref={dialogRef}
      className="detail__lightbox fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Screenshot viewer"
      tabIndex={-1}
      onClick={onClose}
    >
      <img src={src} alt="" className="detail__lightbox-img" />
    </div>
  );
}
