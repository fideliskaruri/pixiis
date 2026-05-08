/**
 * Toast — Editorial pill notifications.
 *
 * Render-only: state lives in ToastContext. Entries stack at the
 * bottom-center of the viewport and animate in/out via the
 * `.toast-in` / `.toast-out` classes shipped in animations.css.
 *
 * Editorial restraint: a single accent stripe surfaces only on
 * `kind === 'error'` — info and success use the standard text/elev pair.
 */

import './Toast.css';

export type ToastKind = 'info' | 'success' | 'error';

export interface ToastEntry {
  id: number;
  message: string;
  kind: ToastKind;
}

interface Props {
  entries: ToastEntry[];
  onDismiss: (id: number) => void;
}

export function Toast({ entries, onDismiss }: Props) {
  if (entries.length === 0) return null;

  return (
    <div className="toast-stack" role="region" aria-label="Notifications" aria-live="polite">
      {entries.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`toast toast--${t.kind} toast-in`}
          onClick={() => onDismiss(t.id)}
          aria-label="Dismiss notification"
        >
          {t.kind === 'error' && <span className="toast__mark" aria-hidden="true" />}
          <span className="toast__msg">{t.message}</span>
        </button>
      ))}
    </div>
  );
}
