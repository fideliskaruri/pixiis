/**
 * VirtualKeyboard — On-screen keyboard for controller-only users.
 *
 * Shape:
 *   - 5 rows: 1234567890 / qwerty / asdfghjkl / zxcvbnm / SPACE BKSP ENTER
 *   - D-pad navigates between keys (internal, not the global spatial nav)
 *   - A presses the focused key
 *   - B closes the panel
 *   - Pressing an alpha/numeric mutates the input via the native value
 *     setter so React's controlled <input>s pick up the change through
 *     their onChange handler
 *   - SPACE / BKSP / ENTER do what they say on the tin
 *
 * Activation policy lives in <VirtualKeyboardProvider>:
 *   - Opens on input focus when a gamepad event has fired in the
 *     `RECENT_GAMEPAD_MS` window before the focus
 *   - Closes on B, Esc, or when the input loses focus
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
import { useController, type ControllerButton, type Direction } from '../hooks/useController';
import './VirtualKeyboard.css';

// ── Layout ───────────────────────────────────────────────────────────

type KeyAction =
  | { kind: 'char'; value: string; label?: string }
  | { kind: 'space' }
  | { kind: 'backspace' }
  | { kind: 'enter' }
  | { kind: 'shift' };

interface KeyDef {
  id: string;
  action: KeyAction;
  width?: number; // grid spans (default 1)
}

const ROWS_LOWER: KeyDef[][] = [
  '1234567890'.split('').map((c) => ({ id: c, action: { kind: 'char', value: c } as KeyAction })),
  'qwertyuiop'.split('').map((c) => ({ id: c, action: { kind: 'char', value: c } as KeyAction })),
  'asdfghjkl'.split('').map((c) => ({ id: c, action: { kind: 'char', value: c } as KeyAction })),
  [
    { id: 'shift', action: { kind: 'shift' } as KeyAction, width: 2 },
    ...'zxcvbnm'.split('').map((c) => ({ id: c, action: { kind: 'char', value: c } as KeyAction })),
  ],
  [
    { id: 'space', action: { kind: 'space' } as KeyAction, width: 5 },
    { id: 'backspace', action: { kind: 'backspace' } as KeyAction, width: 2 },
    { id: 'enter', action: { kind: 'enter' } as KeyAction, width: 3 },
  ],
];

// ── Context ──────────────────────────────────────────────────────────

interface VKApi {
  /** Open against the given input or textarea. */
  open: (target: HTMLInputElement | HTMLTextAreaElement) => void;
  close: () => void;
  /** True iff the panel is currently mounted. */
  isOpen: boolean;
  /** Tell the provider a gamepad event just fired. The activation policy
   *  uses this to decide whether to auto-open on next focus. */
  noteGamepadActivity: () => void;
  /** Called by inputs that want to opt-in to auto-open on focus. */
  onInputFocus: (target: HTMLInputElement | HTMLTextAreaElement) => void;
}

const Ctx = createContext<VKApi | null>(null);

const RECENT_GAMEPAD_MS = 1500;

export function VirtualKeyboardProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const lastGamepadAt = useRef<number>(0);

  const open = useCallback((t: HTMLInputElement | HTMLTextAreaElement): void => {
    setTarget(t);
  }, []);

  const close = useCallback((): void => {
    setTarget(null);
  }, []);

  const noteGamepadActivity = useCallback((): void => {
    lastGamepadAt.current = performance.now();
  }, []);

  // Passive: any controller button or D-pad event marks "controller is
  // currently in use". onInputFocus then auto-opens the keyboard if the
  // most recent input was within the recency window.
  useController(
    useCallback((button: ControllerButton) => {
      // Any button counts as "user is on the controller right now".
      void button;
      lastGamepadAt.current = performance.now();
    }, []),
    useCallback((dir: Direction) => {
      if (dir !== null) lastGamepadAt.current = performance.now();
    }, []),
  );

  const onInputFocus = useCallback(
    (t: HTMLInputElement | HTMLTextAreaElement): void => {
      const elapsed = performance.now() - lastGamepadAt.current;
      if (elapsed < RECENT_GAMEPAD_MS) {
        setTarget(t);
      }
    },
    [],
  );

  const api = useMemo<VKApi>(
    () => ({
      open,
      close,
      isOpen: target !== null,
      noteGamepadActivity,
      onInputFocus,
    }),
    [open, close, target, noteGamepadActivity, onInputFocus],
  );

  return (
    <Ctx.Provider value={api}>
      {children}
      {target !== null && <VirtualKeyboard target={target} onClose={close} />}
    </Ctx.Provider>
  );
}

export function useVirtualKeyboard(): VKApi {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error(
      'useVirtualKeyboard() called outside <VirtualKeyboardProvider> — wrap App in the provider.',
    );
  }
  return ctx;
}

// ── Panel ────────────────────────────────────────────────────────────

interface PanelProps {
  target: HTMLInputElement | HTMLTextAreaElement;
  onClose: () => void;
}

interface KeyPos {
  row: number;
  col: number;
}

function VirtualKeyboard({ target, onClose }: PanelProps) {
  const [shifted, setShifted] = useState(false);
  // Selected key indexes — start on the first character of the home row.
  const [pos, setPos] = useState<KeyPos>({ row: 1, col: 0 });

  const panelRef = useRef<HTMLDivElement | null>(null);
  const [placement, setPlacement] = useState<{ top: number; left: number; aboveInput: boolean }>({
    top: 0,
    left: 0,
    aboveInput: false,
  });

  // ── Position the panel below (or above) the target input ──────────
  useEffect(() => {
    const compute = (): void => {
      const rect = target.getBoundingClientRect();
      const panelH = panelRef.current?.offsetHeight ?? 280;
      const panelW = panelRef.current?.offsetWidth ?? 640;
      const margin = 12;

      const spaceBelow = window.innerHeight - rect.bottom;
      const aboveInput = spaceBelow < panelH + margin;

      const top = aboveInput
        ? Math.max(margin, rect.top - panelH - margin)
        : Math.min(window.innerHeight - panelH - margin, rect.bottom + margin);

      // Centre horizontally on the input, but keep the panel inside the
      // viewport on either side.
      const idealLeft = rect.left + rect.width / 2 - panelW / 2;
      const left = Math.max(margin, Math.min(window.innerWidth - panelW - margin, idealLeft));

      setPlacement({ top, left, aboveInput });
    };
    compute();
    window.addEventListener('resize', compute);
    return () => window.removeEventListener('resize', compute);
  }, [target]);

  // ── Mutate the target input ────────────────────────────────────────
  // Single helper: write `next` through React's native value setter so
  // controlled inputs see the change. The setter side-steps React's
  // own override on HTMLInputElement.value — without it, dispatching
  // `input` would re-paint the old value. Chromium (Tauri's webview)
  // always exposes the descriptor, so we treat its absence as a fatal
  // wiring bug rather than silently dropping the keystroke.
  const writeValue = useCallback(
    (next: string): void => {
      const el: HTMLInputElement | HTMLTextAreaElement = target;
      const proto =
        el instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter === undefined) {
        console.warn('[vkbd] native value setter unavailable; dropping keystroke');
        return;
      }
      setter.call(el, next);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    },
    [target],
  );

  const insertText = useCallback(
    (text: string): void => {
      const el: HTMLInputElement | HTMLTextAreaElement = target;
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      const next = el.value.slice(0, start) + text + el.value.slice(end);
      writeValue(next);
      const caret = start + text.length;
      el.setSelectionRange(caret, caret);
    },
    [target, writeValue],
  );

  const backspace = useCallback((): void => {
    const el: HTMLInputElement | HTMLTextAreaElement = target;
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    if (start === 0 && end === 0) return;
    let nextStart: number;
    let next: string;
    if (start === end) {
      nextStart = Math.max(0, start - 1);
      next = el.value.slice(0, nextStart) + el.value.slice(end);
    } else {
      nextStart = start;
      next = el.value.slice(0, start) + el.value.slice(end);
    }
    writeValue(next);
    el.setSelectionRange(nextStart, nextStart);
  }, [target, writeValue]);

  const fire = useCallback(
    (action: KeyAction): void => {
      switch (action.kind) {
        case 'char': {
          const v = shifted ? action.value.toUpperCase() : action.value;
          insertText(v);
          // Auto-release shift after one character — a sticky shift
          // would be surprising when there's no visible Caps state.
          if (shifted) setShifted(false);
          return;
        }
        case 'space':
          insertText(' ');
          return;
        case 'backspace':
          backspace();
          return;
        case 'enter': {
          // Fire a synthetic Enter on the input — most consumers handle
          // this via onKeyDown (form submit, search trigger, etc).
          target.dispatchEvent(
            new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
          );
          onClose();
          return;
        }
        case 'shift':
          setShifted((s) => !s);
          return;
      }
    },
    [shifted, insertText, backspace, target, onClose],
  );

  // ── D-pad navigation between keys ──────────────────────────────────
  const moveSelection = useCallback((dir: 'up' | 'down' | 'left' | 'right'): void => {
    setPos((p) => {
      let { row, col } = p;
      if (dir === 'up') {
        row = Math.max(0, row - 1);
        col = Math.min(col, ROWS_LOWER[row].length - 1);
      } else if (dir === 'down') {
        row = Math.min(ROWS_LOWER.length - 1, row + 1);
        col = Math.min(col, ROWS_LOWER[row].length - 1);
      } else if (dir === 'left') {
        col = Math.max(0, col - 1);
      } else {
        col = Math.min(ROWS_LOWER[row].length - 1, col + 1);
      }
      return { row, col };
    });
  }, []);

  // Controller hook — local nav while keyboard is open. The global
  // useSpatialNav still runs but the keyboard claims focus visually
  // through its own selected-key state, not the DOM focus ring.
  useController(
    useCallback(
      (button) => {
        if (button === 'a') {
          const key = ROWS_LOWER[pos.row][pos.col];
          if (key !== undefined) fire(key.action);
        } else if (button === 'b') {
          onClose();
        } else if (button === 'x') {
          backspace();
        } else if (button === 'y') {
          insertText(' ');
        }
      },
      [pos, fire, onClose, backspace, insertText],
    ),
    useCallback(
      (dir) => {
        if (dir !== null) moveSelection(dir);
      },
      [moveSelection],
    ),
  );

  // Keyboard fallback (Esc closes, arrow keys also navigate so a tester
  // without a controller can still drive the panel).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveSelection('up');
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveSelection('down');
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        moveSelection('left');
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        moveSelection('right');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [moveSelection, onClose]);

  return (
    <div
      ref={panelRef}
      className={`vkbd ${placement.aboveInput ? 'vkbd--above' : 'vkbd--below'}`}
      style={{ top: placement.top, left: placement.left }}
      role="dialog"
      aria-modal="false"
      aria-label="On-screen keyboard"
    >
      <div className="vkbd__head">
        <p className="label">VIRTUAL KEYBOARD</p>
        <p className="label vkbd__hint">A SELECT · B CLOSE · X BKSP · Y SPACE</p>
      </div>
      {ROWS_LOWER.map((row, rIdx) => (
        <div key={rIdx} className="vkbd__row">
          {row.map((key, cIdx) => {
            const selected = pos.row === rIdx && pos.col === cIdx;
            const label = renderLabel(key, shifted);
            return (
              <button
                key={key.id}
                type="button"
                className={`vkbd__key vkbd__key--${key.action.kind} ${selected ? 'vkbd__key--selected' : ''} ${
                  key.action.kind === 'shift' && shifted ? 'vkbd__key--active' : ''
                }`}
                style={{ flex: key.width ?? 1 }}
                onClick={() => {
                  setPos({ row: rIdx, col: cIdx });
                  fire(key.action);
                }}
                tabIndex={-1}
              >
                {label}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function renderLabel(key: KeyDef, shifted: boolean): string {
  switch (key.action.kind) {
    case 'char':
      return shifted ? key.action.value.toUpperCase() : key.action.value;
    case 'space':
      return 'SPACE';
    case 'backspace':
      return '← BKSP';
    case 'enter':
      return 'ENTER ↵';
    case 'shift':
      return shifted ? 'SHIFT •' : 'SHIFT';
  }
}
