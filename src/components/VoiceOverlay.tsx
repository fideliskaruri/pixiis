/**
 * VoiceOverlay — Live transcription panel.
 *
 * Listens for backend events:
 *   - `voice:state`   → { state: 'idle' | 'listening' | 'processing' }
 *   - `voice:partial` → { text: string }   (streaming)
 *   - `voice:final`   → { text: string }   (commit)
 *
 * Plus a frontend-only error event dispatched by `useVoiceTrigger` and
 * the SearchBar mic button when `voiceStart` / `voiceStop` rejects:
 *   - window event `pixiis:voice-ui-error` → { kind, message }
 *
 * State labels (per UX research § 5.4):
 *   - listening              → `LISTENING`
 *   - listening + 1.5s no audio
 *                            → `STILL LISTENING…` (label flip only,
 *                               overlay stays mounted)
 *   - processing             → `TRANSCRIBING`
 *   - error: model_missing   → `MODEL NOT INSTALLED · Open Settings`
 *                              (press A to nav to Settings → Voice)
 *   - error: mic_denied      → `MICROPHONE DENIED · check Windows privacy`
 *
 * Visibility:
 *   - Fade in 150 ms when state goes to `listening` (or any error).
 *   - Fade out 400 ms when state returns to `idle`.
 *   - Auto-hide 5 s after the most recent `voice:final` if no further
 *     partials arrive.
 *   - Errors auto-hide after 5 s as well.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { useNavigate } from 'react-router-dom';
import {
  VOICE_UI_ERROR_EVENT,
  type VoiceUiErrorKind,
} from '../hooks/useVoiceTrigger';
import { useQuickSearch } from './QuickSearch';
import './VoiceOverlay.css';

type VoiceState = 'idle' | 'listening' | 'processing';

interface VoiceStateEvent {
  state: VoiceState;
}
interface VoiceTextEvent {
  text: string;
}
interface VoiceUiErrorDetail {
  kind: VoiceUiErrorKind;
  message: string;
}

const AUTO_HIDE_MS = 5000;
const FADE_OUT_MS = 400;
/// Per § 5.4: after this many ms of `listening` with no `voice:partial`
/// landing, flip the label to `STILL LISTENING…` so the user knows the
/// trigger is being read but no audio is being heard.
const STILL_LISTENING_DELAY_MS = 1500;

/// Snapshot of the focused element at the moment voice recording starts.
/// We capture on `voice:state listening` so the user can RT, look away
/// from the search bar to think, and still have the final transcript
/// land where they expected. If the snapshot is no longer focusable on
/// `voice:final`, we fall back to QuickSearch.
function captureFocusedInput(): HTMLInputElement | HTMLTextAreaElement | null {
  const el = document.activeElement;
  if (el instanceof HTMLInputElement) {
    const t = el.type.toLowerCase();
    if (t === 'text' || t === 'search' || t === '' || t === 'url') return el;
  }
  if (el instanceof HTMLTextAreaElement) return el;
  return null;
}

/// Set `input.value = text` and fire React's expected event so controlled
/// `<input value={state} onChange>` consumers see the change. Without
/// the synthesised event, React's onChange never fires and the user's
/// transcript appears in the DOM but vanishes on the next re-render.
function dispatchTextIntoInput(
  input: HTMLInputElement | HTMLTextAreaElement,
  text: string,
): void {
  // React patches the `value` setter on prototypes. To trip its change
  // detection we need to use the *native* setter, then dispatch an
  // `input` event the React listener will pick up.
  const proto =
    input instanceof HTMLInputElement
      ? HTMLInputElement.prototype
      : HTMLTextAreaElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter !== undefined) {
    setter.call(input, text);
  } else {
    input.value = text;
  }
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

export function VoiceOverlay() {
  const navigate = useNavigate();
  const { openWithQuery } = useQuickSearch();
  const [state, setState] = useState<VoiceState>('idle');
  const [partial, setPartial] = useState('');
  const [finalText, setFinalText] = useState('');
  const [errorKind, setErrorKind] = useState<VoiceUiErrorKind | null>(null);
  const [stillListening, setStillListening] = useState(false);
  // Snapshotted at session start so the dispatch on `voice:final`
  // doesn't lose track when the user navigates the focus during
  // recording.
  const focusedInputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  // Mirrors `openWithQuery` into a ref so the long-lived `voice:final`
  // listener (subscribed once on mount with `[]` deps) can call the
  // freshest version without re-subscribing on every render.
  const openWithQueryRef = useRef(openWithQuery);
  useEffect(() => {
    openWithQueryRef.current = openWithQuery;
  }, [openWithQuery]);

  // Two-phase visibility: `mounted` keeps the DOM alive long enough for
  // the fade-out animation to play; `visible` drives the actual class.
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);

  const autoHideTimer = useRef<number | null>(null);
  const unmountTimer = useRef<number | null>(null);
  const stillListeningTimer = useRef<number | null>(null);

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
          // A new session is starting — clear any prior error so the
          // overlay reads `LISTENING` instead of `MODEL NOT INSTALLED`.
          setErrorKind(null);
          setStillListening(false);
          // Snapshot what was focused at start time. We dispatch the
          // final transcript here on `voice:final` so the user's input
          // is the one that wins, even if focus drifted during the
          // recording.
          focusedInputRef.current = captureFocusedInput();
        }
      }),
      listen<VoiceTextEvent>('voice:partial', (e) => {
        setPartial(e.payload?.text ?? '');
        // Any partial means audio was heard — drop the "still listening"
        // label.
        setStillListening(false);
      }),
      listen<VoiceTextEvent>('voice:final', (e) => {
        const text = e.payload?.text ?? '';
        setFinalText(text);
        setPartial('');
        // Per § 5.4: dispatch the transcript into whatever was focused
        // when recording started. Fall back to QuickSearch (with the
        // text pre-filled) when no input was focused — that way the
        // user always lands on a surface that can act on what they
        // said. Empty / whitespace-only transcripts are treated as a
        // silent abort.
        if (text.trim() !== '') {
          const target = focusedInputRef.current;
          const stillInDom =
            target !== null && document.body.contains(target);
          if (stillInDom && target !== null) {
            dispatchTextIntoInput(target, text);
            // Re-focus so the user can immediately edit / press Enter
            // — Tauri's webview can drop focus when the overlay
            // mounted underneath the focused control.
            target.focus();
          } else {
            openWithQueryRef.current(text);
          }
        }
        focusedInputRef.current = null;
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

  // UI-error subscription — dispatched from `useVoiceTrigger` /
  // SearchBar mic when `voiceStart` rejects.
  useEffect(() => {
    const onError = (raw: Event): void => {
      const e = raw as CustomEvent<VoiceUiErrorDetail>;
      const kind = e.detail?.kind ?? 'unknown';
      setErrorKind(kind);
      // Force the overlay to render even if the backend never emitted a
      // `voice:state listening` (because `voice_start` rejected before
      // it could).
      setMounted(true);
      requestAnimationFrame(() => setVisible(true));
      // Auto-hide errors after the same window as `final` text.
      if (autoHideTimer.current !== null) {
        window.clearTimeout(autoHideTimer.current);
      }
      autoHideTimer.current = window.setTimeout(() => {
        setErrorKind(null);
        setState('idle');
        autoHideTimer.current = null;
      }, AUTO_HIDE_MS);
    };
    window.addEventListener(VOICE_UI_ERROR_EVENT, onError);
    return () => window.removeEventListener(VOICE_UI_ERROR_EVENT, onError);
  }, []);

  // State → visibility cross-fade.
  useEffect(() => {
    const showy = state === 'listening' || state === 'processing' || errorKind !== null;
    if (showy) {
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
  }, [state, errorKind]);

  // "Still listening…" label flip after STILL_LISTENING_DELAY_MS without
  // any partial arriving. Reset on every transition into `listening` and
  // every partial.
  useEffect(() => {
    if (stillListeningTimer.current !== null) {
      window.clearTimeout(stillListeningTimer.current);
      stillListeningTimer.current = null;
    }
    if (state === 'listening' && partial === '' && !stillListening) {
      stillListeningTimer.current = window.setTimeout(() => {
        setStillListening(true);
        stillListeningTimer.current = null;
      }, STILL_LISTENING_DELAY_MS);
    }
    return () => {
      if (stillListeningTimer.current !== null) {
        window.clearTimeout(stillListeningTimer.current);
        stillListeningTimer.current = null;
      }
    };
  }, [state, partial, stillListening]);

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
      if (stillListeningTimer.current !== null) window.clearTimeout(stillListeningTimer.current);
    };
  }, []);

  // Click handler for the model-missing state — single-press to Settings.
  const goToVoiceSettings = useCallback(() => {
    setErrorKind(null);
    setState('idle');
    navigate('/settings');
  }, [navigate]);

  if (!mounted) return null;

  // Resolve the state label per § 5.4. Errors win over normal flow so a
  // failed `voice_start` reads `MODEL NOT INSTALLED` instead of `LISTENING`.
  const stateLabel = (() => {
    if (errorKind === 'model_missing') return 'MODEL NOT INSTALLED · Open Settings';
    if (errorKind === 'mic_denied') return 'MICROPHONE DENIED · check Windows privacy';
    if (errorKind === 'unknown') return 'VOICE ERROR';
    if (state === 'processing') return 'TRANSCRIBING';
    if (state === 'listening') return stillListening ? 'STILL LISTENING…' : 'LISTENING';
    return 'DONE';
  })();

  const isError = errorKind !== null;

  return (
    <div
      className={`voice-overlay ${visible ? 'voice-overlay--visible' : 'voice-overlay--hiding'} ${
        isError ? 'voice-overlay--error' : ''
      }`}
      role="status"
      aria-live="polite"
    >
      <div className="voice-overlay__bar" aria-hidden="true">
        <span className="voice-overlay__dot" />
        <p className="label voice-overlay__state">{stateLabel}</p>
      </div>
      <div className="voice-overlay__readout">
        {errorKind === 'model_missing' && (
          <button
            type="button"
            className="voice-overlay__action"
            onClick={goToVoiceSettings}
            data-focusable
          >
            Open Settings → Voice
          </button>
        )}
        {!isError && finalText !== '' && (
          <p className="voice-overlay__final">{finalText}</p>
        )}
        {!isError && partial !== '' && (
          <p className="voice-overlay__partial">{partial}</p>
        )}
        {!isError && finalText === '' && partial === '' && state === 'listening' && (
          <p className="voice-overlay__partial voice-overlay__partial--empty">
            Speak…
          </p>
        )}
      </div>
    </div>
  );
}
