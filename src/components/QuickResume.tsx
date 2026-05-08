/**
 * QuickResume — Modal carousel of the last five played games.
 *
 * Triggered by the controller Start button (or a programmatic open()
 * exposed via context). Reads from useLibrary(), sorts by last_played
 * desc, slices 5. A → launch via bridge.launchGame(id). B / Esc closes.
 *
 * Editorial style: black backdrop at 80% opacity, content on --bg-elev,
 * serif heading, small-caps card metadata. Cross-fades 200 ms.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { useController } from '../hooks/useController';
import { useLibrary } from '../api/LibraryContext';
import { imageUrl, launchGame, type AppEntry } from '../api/bridge';
import { useToast } from '../api/ToastContext';
import './QuickResume.css';

interface QuickResumeApi {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const Ctx = createContext<QuickResumeApi | null>(null);

export function useQuickResume(): QuickResumeApi {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error(
      'useQuickResume() called outside <QuickResume> — mount the component at the app root.',
    );
  }
  return ctx;
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

function formatLastPlayed(unixSeconds: number): string {
  if (unixSeconds <= 0) return '';
  const ms = unixSeconds * 1000;
  const elapsed = Date.now() - ms;
  const day = 24 * 60 * 60 * 1000;
  const days = Math.floor(elapsed / day);
  if (days <= 0) return 'TODAY';
  if (days === 1) return 'YESTERDAY';
  if (days < 7) return `${days}D AGO`;
  if (days < 30) return `${Math.floor(days / 7)}W AGO`;
  if (days < 365) return `${Math.floor(days / 30)}MO AGO`;
  return `${Math.floor(days / 365)}Y AGO`;
}

export function QuickResume({ children }: { children?: ReactNode }) {
  const [isOpen, setOpen] = useState(false);
  const open = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);

  const api = useMemo<QuickResumeApi>(
    () => ({ open, close, isOpen }),
    [open, close, isOpen],
  );

  // Start button on the controller — open from anywhere.
  // We intentionally always-on mount this listener (even when closed)
  // so Start works as a global shortcut.
  useController(
    useCallback(
      (button) => {
        if (button === 'start') {
          setOpen((v) => !v);
        }
      },
      [],
    ),
  );

  return (
    <Ctx.Provider value={api}>
      {children}
      {isOpen && <Panel onClose={close} />}
    </Ctx.Provider>
  );
}

function Panel({ onClose }: { onClose: () => void }) {
  const { games } = useLibrary();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [selected, setSelected] = useState(0);
  const [launching, setLaunching] = useState<string | null>(null);
  const restoreFocus = useRef<Element | null>(null);

  const cards = useMemo(
    () =>
      games
        .filter((g) => g.is_game && g.last_played > 0)
        .sort((a, b) => b.last_played - a.last_played)
        .slice(0, 5),
    [games],
  );

  // Clamp selection during render if the list shrunk under us (e.g.
  // library refresh) — calling setState in an effect would just trigger
  // an extra render. The displayed selection is `clampedSelected`, while
  // `selected` stays as the raw cursor for the "remember position" feel.
  const clampedSelected =
    cards.length === 0 ? 0 : Math.min(selected, cards.length - 1);

  // Save the active element so we can return focus when the panel
  // closes — keeps controller / keyboard users where they were.
  useEffect(() => {
    restoreFocus.current = document.activeElement;
    return () => {
      const el = restoreFocus.current;
      if (el instanceof HTMLElement) el.focus();
    };
  }, []);

  const launch = useCallback(
    async (card: AppEntry): Promise<void> => {
      if (launching !== null) return;
      setLaunching(card.id);
      try {
        await launchGame(card.id);
        toast(`Launching ${card.name}`, 'success');
        onClose();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        toast(`Failed to launch: ${msg}`, 'error');
        setLaunching(null);
      }
    },
    [launching, onClose, toast],
  );

  // Esc → close, arrows cycle, Enter launches. Captured here rather than
  // relying on global handlers so the dialog owns its own dismissal
  // semantics even if a focused element swallows the key.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setSelected((i) => Math.max(0, i - 1));
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        setSelected((i) => Math.min(Math.max(0, cards.length - 1), i + 1));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const card = cards[clampedSelected];
        if (card !== undefined) void launch(card);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [cards, clampedSelected, launch, onClose]);

  // Controller: D-pad left/right cycles, A launches, B closes.
  useController(
    useCallback(
      (button) => {
        if (button === 'b' || button === 'start') {
          onClose();
        } else if (button === 'a') {
          const card = cards[clampedSelected];
          if (card !== undefined) void launch(card);
        }
      },
      [cards, clampedSelected, launch, onClose],
    ),
    useCallback(
      (dir) => {
        if (dir === 'left') setSelected((i) => Math.max(0, i - 1));
        else if (dir === 'right') {
          setSelected((i) => Math.min(Math.max(0, cards.length - 1), i + 1));
        }
      },
      [cards.length],
    ),
  );

  return (
    <div
      className="qresume fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Quick Resume"
      onClick={(e) => {
        // Backdrop dismiss — clicks landing directly on the wrapper
        // close, but anything inside the panel keeps the dialog open.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="qresume__panel">
        <header className="qresume__head">
          <p className="label">RECENTLY PLAYED</p>
          <h2 className="qresume__title display">Quick Resume</h2>
          <button
            className="qresume__close"
            onClick={onClose}
            aria-label="Close Quick Resume"
            data-focusable
          >
            ✕
          </button>
        </header>

        {cards.length === 0 ? (
          <div className="qresume__empty">
            <p className="label">NOTHING YET</p>
            <p className="qresume__empty-body">
              Your last five played games will surface here once you’ve
              opened a few.
            </p>
          </div>
        ) : (
          <div className="qresume__rail" role="list">
            {cards.map((card, i) => {
              const sourceLabel =
                SOURCE_LABELS[card.source] ?? card.source.toUpperCase();
              const recency = formatLastPlayed(card.last_played);
              const art = imageUrl(card.art_url);
              const isSelected = i === clampedSelected;
              const isLaunching = launching === card.id;
              return (
                <button
                  key={card.id}
                  type="button"
                  role="listitem"
                  className={`qresume__card ${isSelected ? 'qresume__card--selected' : ''}`}
                  onClick={() => {
                    setSelected(i);
                    void launch(card);
                  }}
                  onMouseEnter={() => setSelected(i)}
                  data-focusable
                  aria-label={`Resume ${card.name}`}
                  disabled={launching !== null && launching !== card.id}
                >
                  <div className="qresume__art">
                    {art !== '' && <img src={art} alt="" loading="lazy" />}
                  </div>
                  <div className="qresume__caption">
                    <p className="label qresume__source">{sourceLabel}</p>
                    <h3 className="qresume__name">{card.name}</h3>
                    <p className="label qresume__recency">{recency}</p>
                  </div>
                  {isLaunching && (
                    <span className="label qresume__status">LAUNCHING…</span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        <footer className="qresume__foot">
          <button
            className="qresume__link label"
            onClick={() => {
              onClose();
              navigate('/');
            }}
            data-focusable
          >
            ALL GAMES →
          </button>
          <p className="label qresume__legend">A LAUNCH · B CLOSE</p>
        </footer>
      </div>
    </div>
  );
}
