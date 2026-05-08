/**
 * ToastContext — Global notification system.
 *
 * `useToast()` returns a `toast(message, kind?)` function that any
 * component anywhere in the tree can call. A single <ToastProvider>
 * mounts at the app root and renders the actual stack via the <Toast>
 * component (which lives next to the provider so the markup is
 * co-located with the state that drives it).
 *
 * Replaces what was the PySide6 Toast widget — same shape, web style.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { Toast, type ToastEntry, type ToastKind } from '../components/Toast';

interface ToastApi {
  toast: (message: string, kind?: ToastKind) => void;
}

const Ctx = createContext<ToastApi | null>(null);

const TOAST_TTL_MS = 2500;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [entries, setEntries] = useState<ToastEntry[]>([]);
  // Counter survives across calls — using Date.now() risks collisions
  // when two toasts fire in the same tick.
  const nextId = useRef(0);

  const dismiss = useCallback((id: number): void => {
    setEntries((list) => list.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((message: string, kind: ToastKind = 'info'): void => {
    const id = nextId.current++;
    setEntries((list) => [...list, { id, message, kind }]);
    window.setTimeout(() => {
      dismiss(id);
    }, TOAST_TTL_MS);
  }, [dismiss]);

  const api = useMemo<ToastApi>(() => ({ toast }), [toast]);

  return (
    <Ctx.Provider value={api}>
      {children}
      <Toast entries={entries} onDismiss={dismiss} />
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(Ctx);
  if (ctx === null) {
    throw new Error(
      'useToast() called outside <ToastProvider> — wrap App in the provider.',
    );
  }
  return ctx;
}
