/**
 * useVoiceTrigger — Wires the configured `controller.voice_trigger` to
 * the voice push-to-talk pipeline.
 *
 * Without this hook the user-facing "RT shortcut" in `controller.voice_trigger`
 * is a config-only setting: `useController` exposes `getRightTrigger()` (and
 * its bumper-button neighbours) but no consumer ever calls it, so the voice
 * overlay never opens from a controller. The user complaint
 *
 *   > "the rt shortcut and overlay don't even show up"
 *
 * is literally that. This hook closes the loop:
 *
 * 1. On mount, read `controller.voice_trigger` from `getConfig()`. Default
 *    to `'rt'` (matches `SettingsPage::DEFAULTS`). Re-read once at mount;
 *    we don't observe live config changes — the next app launch picks up
 *    a Settings change. (Cheap, predictable.)
 * 2. Poll the gamepad at ~60 Hz via `requestAnimationFrame` — the same
 *    cadence the rest of the controller stack uses. Detect the trigger's
 *    rising / falling edge; fire `voiceStart()` / `voiceStop()`
 *    accordingly. We coalesce so a stop can never run without a prior
 *    start.
 * 3. Tolerate the existing `useController` / `useBumperNav` /
 *    `useSpatialNav` poll loops — each subscribes to its own RAF; one
 *    more is fine.
 *
 * Mount once, globally, from `App.tsx` next to `useBumperNav()`.
 */

import { useEffect, useRef, useState } from 'react';
import { getConfig, voiceStart, voiceStop } from '../api/bridge';

type VoiceTriggerKind = 'rt' | 'lt' | 'hold_y' | 'hold_x';

/// Dispatch a frontend-only error to the VoiceOverlay so it can render a
/// clean state label (`MODEL NOT INSTALLED`, `MICROPHONE DENIED`, …)
/// instead of a raw toast. The overlay subscribes via `window.addEventListener`.
/// `kind` is the discriminator the overlay reads to pick its copy.
export type VoiceUiErrorKind = 'model_missing' | 'mic_denied' | 'unknown';
export const VOICE_UI_ERROR_EVENT = 'pixiis:voice-ui-error';

interface VoiceUiErrorDetail {
  kind: VoiceUiErrorKind;
  message: string;
}

function classifyVoiceError(err: unknown): VoiceUiErrorKind {
  const msg = (err instanceof Error ? err.message : String(err)).toLowerCase();
  // Backend wraps init failure as `voice unavailable: <reason>` and
  // includes the missing-model phrase from `model.rs`. See
  // `commands/voice.rs::VoiceServiceSlot::get` and `lib.rs::run::setup`.
  if (msg.includes('whisper model') || msg.includes('voice unavailable')) {
    return 'model_missing';
  }
  if (
    msg.includes('mic') ||
    msg.includes('microphone') ||
    msg.includes('permission') ||
    msg.includes('denied') ||
    msg.includes('access')
  ) {
    return 'mic_denied';
  }
  return 'unknown';
}

function dispatchVoiceUiError(err: unknown): void {
  const detail: VoiceUiErrorDetail = {
    kind: classifyVoiceError(err),
    message: err instanceof Error ? err.message : String(err),
  };
  window.dispatchEvent(new CustomEvent<VoiceUiErrorDetail>(VOICE_UI_ERROR_EVENT, { detail }));
}

const DEFAULT_TRIGGER: VoiceTriggerKind = 'rt';
/// Analog-trigger threshold. The Standard Gamepad spec reports `value`
/// in [0, 1]; we treat ≥ 0.5 as "held" with a small hysteresis on the
/// release side so partial pulls don't chatter.
const ANALOG_PRESS_THRESHOLD = 0.5;
const ANALOG_RELEASE_THRESHOLD = 0.3;
/// Y / X are digital buttons — `pressed` is reliable; no threshold.

function readTriggerKindFromConfig(cfg: Record<string, unknown>): VoiceTriggerKind {
  const controllerSection = cfg['controller'];
  if (controllerSection !== null && typeof controllerSection === 'object') {
    const v = (controllerSection as Record<string, unknown>)['voice_trigger'];
    if (v === 'rt' || v === 'lt' || v === 'hold_y' || v === 'hold_x') return v;
  }
  // Some config shapes flatten — accept dotted form too.
  const dotted = cfg['controller.voice_trigger'];
  if (dotted === 'rt' || dotted === 'lt' || dotted === 'hold_y' || dotted === 'hold_x') {
    return dotted;
  }
  return DEFAULT_TRIGGER;
}

/**
 * Read the current "is the configured trigger held" state from the
 * connected gamepad. Returns `false` when no gamepad is connected; we
 * never want a missing pad to pretend the trigger is pressed.
 */
function isTriggerHeld(kind: VoiceTriggerKind, prevHeld: boolean): boolean {
  const gp = navigator.getGamepads()[0];
  if (gp === null || gp === undefined) return false;

  switch (kind) {
    case 'rt': {
      // Standard Gamepad button 7 = Right Trigger.
      const v = gp.buttons[7]?.value ?? (gp.buttons[7]?.pressed === true ? 1 : 0);
      return prevHeld ? v >= ANALOG_RELEASE_THRESHOLD : v >= ANALOG_PRESS_THRESHOLD;
    }
    case 'lt': {
      // Standard Gamepad button 6 = Left Trigger.
      const v = gp.buttons[6]?.value ?? (gp.buttons[6]?.pressed === true ? 1 : 0);
      return prevHeld ? v >= ANALOG_RELEASE_THRESHOLD : v >= ANALOG_PRESS_THRESHOLD;
    }
    case 'hold_y':
      // Standard Gamepad button 3 = Y on Xbox layout.
      return gp.buttons[3]?.pressed === true;
    case 'hold_x':
      // Standard Gamepad button 2 = X on Xbox layout.
      return gp.buttons[2]?.pressed === true;
  }
}

/**
 * Mount once globally. Returns the read trigger kind so a debug panel
 * could surface it; callers normally ignore the return value.
 */
export function useVoiceTrigger(): VoiceTriggerKind {
  const [trigger, setTrigger] = useState<VoiceTriggerKind>(DEFAULT_TRIGGER);
  // We track held-ness in a ref so the RAF loop can read the latest
  // value without re-subscribing every tick. `voiceActive` mirrors the
  // backend session state — we never call `voiceStop()` without a prior
  // `voiceStart()` succeeding.
  const heldRef = useRef(false);
  const voiceActiveRef = useRef(false);
  const startInFlightRef = useRef(false);

  // Load the configured trigger once. If the call fails (older backend
  // without `config_get`) we silently keep the default — the launcher
  // still works, the user just can't override RT.
  useEffect(() => {
    let cancelled = false;
    void getConfig()
      .then((cfg) => {
        if (cancelled) return;
        setTrigger(readTriggerKindFromConfig(cfg));
      })
      .catch(() => {
        // Stay on default. eprintln-equivalent — but we don't want a
        // toast here; this is a soft-failure path.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let raf = 0;
    let cancelled = false;

    const tick = (): void => {
      if (cancelled) return;
      const held = isTriggerHeld(trigger, heldRef.current);

      // Rising edge — start a session if one isn't already running.
      if (held && !heldRef.current && !voiceActiveRef.current && !startInFlightRef.current) {
        startInFlightRef.current = true;
        // Optimistically mark active so a brief overshoot of `held` past
        // the start promise doesn't stack `voice_start` calls; the
        // backend would reject the second one with `InvalidArg`, which
        // we don't want to surface as a toast.
        voiceActiveRef.current = true;
        void voiceStart()
          .catch((err: unknown) => {
            // The backend returned an error — flip the flags back so a
            // second press can retry, and dispatch a typed UI error so
            // the VoiceOverlay can render a clean state label
            // (MODEL NOT INSTALLED · Open Settings) instead of a raw
            // toast. See `VoiceOverlay.tsx::voiceErrorState`.
            voiceActiveRef.current = false;
            dispatchVoiceUiError(err);
            // eslint-disable-next-line no-console
            console.warn('[useVoiceTrigger] voiceStart failed', err);
          })
          .finally(() => {
            startInFlightRef.current = false;
          });
      }

      // Falling edge — stop the session iff we actually started one.
      // We also wait for any in-flight `voice_start` so a fast tap
      // doesn't race the start promise: stopping before the backend has
      // taken the session lock yields a "no active voice session" error.
      if (!held && heldRef.current && voiceActiveRef.current) {
        voiceActiveRef.current = false;
        const inFlight = startInFlightRef.current;
        const doStop = (): Promise<unknown> =>
          voiceStop().catch((err: unknown) => {
            dispatchVoiceUiError(err);
            // eslint-disable-next-line no-console
            console.warn('[useVoiceTrigger] voiceStop failed', err);
          });
        if (inFlight) {
          // Defer the stop until the next animation frame; by then the
          // start promise has typically resolved. We don't await
          // explicitly because the closure over the promise would prevent
          // re-entering the tick loop.
          requestAnimationFrame(() => {
            void doStop();
          });
        } else {
          void doStop();
        }
      }

      heldRef.current = held;
      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      // If the user navigates / unmounts mid-session, close it cleanly.
      if (voiceActiveRef.current) {
        voiceActiveRef.current = false;
        void voiceStop().catch(() => {
          // best-effort
        });
      }
    };
  }, [trigger]);

  return trigger;
}
