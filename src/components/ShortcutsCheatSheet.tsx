/**
 * ShortcutsCheatSheet — Magazine-style keyboard + gamepad reference.
 *
 * Opened by F1 anywhere in the app. Three columns: Key / Action /
 * Context. Static map — when a new shortcut lands elsewhere in the
 * app, add it to SHORTCUTS so the cheat sheet stays in sync.
 *
 * Editorial style: same scrim weight as QuickResume / QuickSearch,
 * Fraunces title, Inter body, IBM Plex Mono for the keys.
 */

import { useCallback, useEffect, useState } from 'react';
import { useController } from '../hooks/useController';
import { useActionFooter } from '../api/ActionFooterContext';
import './ShortcutsCheatSheet.css';

interface Shortcut {
  keys: string;
  action: string;
  context: string;
  /** When set, this row is keyboard-only (no gamepad equivalent). */
  kbOnly?: boolean;
}

const KEYBOARD: Shortcut[] = [
  { keys: 'Ctrl + K', action: 'Open Quick Search', context: 'Anywhere' },
  { keys: 'F1', action: 'Show this cheat sheet', context: 'Anywhere', kbOnly: true },
  { keys: 'F11', action: 'Toggle fullscreen', context: 'Anywhere', kbOnly: true },
  { keys: 'Esc', action: 'Close modal / dismiss', context: 'Modals' },
  { keys: 'Enter', action: 'Open or launch', context: 'Tile · Search row' },
  { keys: 'Y', action: 'Toggle favourite', context: 'Tile' },
  { keys: '↑ ↓ ← →', action: 'Move focus', context: 'Grid · Lists' },
  { keys: 'Tab / Shift+Tab', action: 'Cycle focusables', context: 'Anywhere', kbOnly: true },
];

const GAMEPAD: Shortcut[] = [
  { keys: 'X', action: 'Open Quick Search', context: 'Anywhere' },
  { keys: 'Start', action: 'Toggle Quick Resume', context: 'Anywhere' },
  { keys: 'A', action: 'Select / Launch', context: 'Tile · Modal' },
  { keys: 'B', action: 'Back / Close', context: 'Modal · Detail' },
  { keys: 'Y', action: 'Favourite (tile) · Detail (search)', context: 'Tile · Search' },
  { keys: 'D-Pad', action: 'Move focus', context: 'Grid · Lists' },
  { keys: 'LB / RB', action: 'Switch tab (Home/Library/Settings)', context: 'Anywhere' },
  { keys: 'Right Trigger', action: 'Voice (hold)', context: 'Anywhere' },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function ShortcutsCheatSheet({ isOpen, onClose }: Props) {
  // Esc dismisses; B on the controller too. The provider attaches
  // F1 + Y elsewhere; this component only handles inside-modal nav.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  useController(
    useCallback(
      (button) => {
        if (!isOpen) return;
        if (button === 'b') onClose();
      },
      [isOpen, onClose],
    ),
  );

  if (!isOpen) return null;

  return (
    <div
      className="cheats fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard and gamepad shortcuts"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <CheatSheetFooterRegistration />
      <div className="cheats__panel">
        <header className="cheats__head">
          <p className="label">REFERENCE</p>
          <h2 className="cheats__title display">Shortcuts</h2>
          <button
            className="cheats__close"
            onClick={onClose}
            aria-label="Close cheat sheet"
            data-focusable
          >
            ✕
          </button>
        </header>

        <hr className="rule" />

        <div className="cheats__cols">
          <ShortcutTable label="KEYBOARD" rows={KEYBOARD} />
          <ShortcutTable label="GAMEPAD" rows={GAMEPAD} />
        </div>

        <footer className="cheats__foot">
          <p className="label cheats__legend">ESC OR B TO CLOSE</p>
        </footer>
      </div>
    </div>
  );
}

interface TableProps {
  label: string;
  rows: Shortcut[];
}

function ShortcutTable({ label, rows }: TableProps) {
  return (
    <section className="cheats__col">
      <p className="label cheats__col-head">{label}</p>
      <ul className="cheats__list">
        {rows.map((row, i) => (
          <li key={`${label}-${i}`} className="cheats__row">
            <span className="cheats__keys">{row.keys}</span>
            <span className="cheats__action">{row.action}</span>
            <span className="cheats__context label">
              {row.context.toUpperCase()}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// Tiny helper that lives only while the cheat sheet is open. Putting
// the registration inside its own component lets us avoid calling the
// hook conditionally — the parent uses an `if (!isOpen) return null`
// guard, so the hook needs to mount with the modal.
function CheatSheetFooterRegistration() {
  useActionFooter([{ glyph: 'B', verb: 'Close' }]);
  return null;
}

// ── Provider hook ────────────────────────────────────────────────────
//
// Standalone provider so any descendant can call useShortcutsCheats()
// to open the sheet imperatively (e.g. a "?" menu button). The
// component below is mounted at the app root next to QuickSearch.

import { createContext, useContext, useMemo, type ReactNode } from 'react';

interface CheatsApi {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const Ctx = createContext<CheatsApi | null>(null);

export function useShortcutsCheats(): CheatsApi {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error(
      'useShortcutsCheats() called outside <ShortcutsCheatsProvider>.',
    );
  }
  return ctx;
}

export function ShortcutsCheatsProvider({
  children,
}: {
  children?: ReactNode;
}) {
  const [isOpen, setOpen] = useState(false);
  const open = useCallback(() => setOpen(true), []);
  const close = useCallback(() => setOpen(false), []);
  const api = useMemo<CheatsApi>(
    () => ({ open, close, isOpen }),
    [open, close, isOpen],
  );

  // F1 toggles the sheet anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'F1') {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <Ctx.Provider value={api}>
      {children}
      <ShortcutsCheatSheet isOpen={isOpen} onClose={close} />
    </Ctx.Provider>
  );
}
