/**
 * VoiceOverlay — Live transcription panel.
 *
 * Listens for backend events:
 *   - `voice:state`   → { state: 'idle' | 'listening' | 'processing' }
 *   - `voice:partial` → { text: string }   (streaming)
 *   - `voice:final`   → { text: string }   (commit)
 *
 * Visibility:
 *   - Fade in 150 ms when state goes to `listening`
 *   - Fade out 400 ms when state goes to `idle`
 *   - Auto-hide 5 s after the most recent `voice:final` if no further
 *     partials arrive (prevents the panel sticking around forever when
 *     the backend forgets to publish `voice:state: idle`).
 */

import { useEffect, useRef, useState } from 'react';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import './VoiceOverlay.css';

type VoiceState = 'idle' | 'listening' | 'processing';

interface VoiceStateEvent {
  state: VoiceState;
}
interface VoiceTextEvent {
  text: string;
}

const AUTO_HIDE_MS = 5000;
const FADE_OUT_MS = 400;

export function VoiceOverlay() {
  const [state, setState] = useState<VoiceState>('idle');
  const [partial, setPartial] = useState('');
  const [finalText, setFinalText] = useState('');

  // Two-phase visibility: `mounted` keeps the DOM alive long enough for
  // the fade-out animation to play; `visible` drives the actual class.
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);

  const autoHideTimer = useRef<number | null>(null);
  const unmountTimer = useRef<number | null>(null);

  // Subscribe to all three voice events. One effect, one cleanup —
  // unlisten functions are awaited so we never leak listeners on
  // strict-mode double-mount.
  useEffect(() => {
    let unlisten: UnlistenFn[] = [];
    let cancelled = false;

    void Promise.all([
      listen<VoiceStateEvent>('voice:state', (e) => {
        const next = e.payload?.state ?? 'idle';
        setState(next);
        if (next === 'listening') {
          setPartial('');
          setFinalText('');
        }
      }),
      listen<VoiceTextEvent>('voice:partial', (e) => {
        setPartial(e.payload?.text ?? '');
      }),
      listen<VoiceTextEvent>('voice:final', (e) => {
        const text = e.payload?.text ?? '';
        setFinalText(text);
        setPartial('');
      }),
    ]).then((fns) => {
      if (cancelled) {
        for (const fn of fns) fn();
      } else {
        unlisten = fns;
      }
    });

    return () => {
      cancelled = true;
      for (const fn of unlisten) fn();
    };
  }, []);

  // State → visibility cross-fade.
  useEffect(() => {
    if (state === 'listening' || state === 'processing') {
      // Show, cancel any pending unmount.
      if (unmountTimer.current !== null) {
        window.clearTimeout(unmountTimer.current);
        unmountTimer.current = null;
      }
      setMounted(true);
      // Defer the visible flip a tick so the in-animation actually plays
      // when the node was just inserted.
      requestAnimationFrame(() => setVisible(true));
    } else {
      // Idle — fade out, then unmount.
      setVisible(false);
      if (unmountTimer.current !== null) {
        window.clearTimeout(unmountTimer.current);
      }
      unmountTimer.current = window.setTimeout(() => {
        setMounted(false);
        unmountTimer.current = null;
      }, FADE_OUT_MS);
    }
  }, [state]);

  // Auto-hide after a final lands without a follow-up state event.
  useEffect(() => {
    if (autoHideTimer.current !== null) {
      window.clearTimeout(autoHideTimer.current);
      autoHideTimer.current = null;
    }
    if (finalText !== '' && state !== 'listening') {
      autoHideTimer.current = window.setTimeout(() => {
        setState('idle');
        autoHideTimer.current = null;
      }, AUTO_HIDE_MS);
    }
    return () => {
      if (autoHideTimer.current !== null) {
        window.clearTimeout(autoHideTimer.current);
        autoHideTimer.current = null;
      }
    };
  }, [finalText, state]);

  // Tear down both timers on unmount — covers the strict-mode
  // remount path where the auto-hide timer was created in the prior
  // render and the cleanup above hadn't fired yet.
  useEffect(() => {
    return () => {
      if (autoHideTimer.current !== null) window.clearTimeout(autoHideTimer.current);
      if (unmountTimer.current !== null) window.clearTimeout(unmountTimer.current);
    };
  }, []);

  if (!mounted) return null;

  const stateLabel =
    state === 'listening' ? 'LISTENING' : state === 'processing' ? 'TRANSCRIBING' : 'DONE';

  return (
    <div
      className={`voice-overlay ${visible ? 'voice-overlay--visible' : 'voice-overlay--hiding'}`}
      role="status"
      aria-live="polite"
    >
      <div className="voice-overlay__bar" aria-hidden="true">
        <span className="voice-overlay__dot" />
        <p className="label voice-overlay__state">{stateLabel}</p>
      </div>
      <div className="voice-overlay__readout">
        {finalText !== '' && (
          <p className="voice-overlay__final">{finalText}</p>
        )}
        {partial !== '' && (
          <p className="voice-overlay__partial">{partial}</p>
        )}
        {finalText === '' && partial === '' && (
          <p className="voice-overlay__partial voice-overlay__partial--empty">
            Speak…
          </p>
        )}
      </div>
    </div>
  );
}
