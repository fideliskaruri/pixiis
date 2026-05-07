/**
 * SettingsPage — Editorial settings.
 *
 * Two-column layout: section nav on the left, form on the right. Sections
 * cross-fade (200 ms) when switched. All persistence flows through a
 * single Apply button that batches changes into one `config_set` patch.
 *
 * Soft dependencies on other Wave 2 panes:
 *   - Voice partials / TTS speak depend on `wave2/voice` + `wave2/tts`.
 *     Until those merge, the test buttons surface a "Pending …" hint.
 *   - `library:scan:progress` events are emitted by future scanner work;
 *     the page subscribes if they arrive but never blocks on them.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { scanLibrary, voiceStart } from '../api/bridge';
import type { VoiceDevice } from '../api/types/VoiceDevice';
import type { ControllerState } from '../api/types/ControllerState';
import type { TranscriptionEvent } from '../api/types/TranscriptionEvent';
import './SettingsPage.css';

// ── Types ────────────────────────────────────────────────────────────

type SectionKey = 'library' | 'voice' | 'controller' | 'services' | 'about';

const SECTIONS: { key: SectionKey; label: string }[] = [
  { key: 'library', label: 'LIBRARY' },
  { key: 'voice', label: 'VOICE' },
  { key: 'controller', label: 'CONTROLLER' },
  { key: 'services', label: 'SERVICES' },
  { key: 'about', label: 'ABOUT' },
];

type ConfigMap = Record<string, unknown>;

interface SettingsState {
  // Library
  providers: Record<string, boolean>;
  scan_interval_minutes: number;

  // Voice
  voice_model: string;
  voice_device: 'auto' | 'cuda' | 'cpu';
  voice_mic_id: string;
  voice_energy: number;

  // Controller
  ctrl_deadzone: number;
  ctrl_hold_ms: number;
  ctrl_vibration: boolean;
  ctrl_voice_trigger: 'rt' | 'lt' | 'hold_y' | 'hold_x';

  // Services
  rawg_key: string;
  youtube_key: string;
  twitch_connected: boolean;

  // About
  autostart: boolean;
}

const DEFAULTS: SettingsState = {
  providers: {
    steam: true,
    xbox: true,
    epic: true,
    gog: true,
    ea: true,
    startmenu: true,
    folder: true,
  },
  scan_interval_minutes: 60,
  voice_model: 'large-v3',
  voice_device: 'auto',
  voice_mic_id: '',
  voice_energy: 300,
  ctrl_deadzone: 0.15,
  ctrl_hold_ms: 200,
  ctrl_vibration: true,
  ctrl_voice_trigger: 'rt',
  rawg_key: '',
  youtube_key: '',
  twitch_connected: false,
  autostart: false,
};

const PROVIDERS: { key: string; label: string }[] = [
  { key: 'steam', label: 'Steam' },
  { key: 'xbox', label: 'Xbox' },
  { key: 'epic', label: 'Epic' },
  { key: 'gog', label: 'GOG' },
  { key: 'ea', label: 'EA' },
  { key: 'startmenu', label: 'Start Menu' },
  { key: 'folder', label: 'Folder Scanner' },
];

const VOICE_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v3'];
const VOICE_DEVICES: SettingsState['voice_device'][] = ['auto', 'cuda', 'cpu'];
const VOICE_TRIGGERS: { value: SettingsState['ctrl_voice_trigger']; label: string }[] = [
  { value: 'rt', label: 'Right Trigger' },
  { value: 'lt', label: 'Left Trigger' },
  { value: 'hold_y', label: 'Hold Y' },
  { value: 'hold_x', label: 'Hold X' },
];

// ── Helpers ──────────────────────────────────────────────────────────

function readDotted(cfg: ConfigMap, path: string): unknown {
  const keys = path.split('.');
  let node: unknown = cfg;
  for (const k of keys) {
    if (node === null || typeof node !== 'object') return undefined;
    node = (node as Record<string, unknown>)[k];
  }
  return node;
}

function asString(v: unknown, fallback: string): string {
  return typeof v === 'string' ? v : fallback;
}
function asNumber(v: unknown, fallback: number): number {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}
function asBool(v: unknown, fallback: boolean): boolean {
  return typeof v === 'boolean' ? v : fallback;
}

function fromConfig(cfg: ConfigMap): SettingsState {
  const enabled = readDotted(cfg, 'library.providers');
  const enabledSet = new Set(
    Array.isArray(enabled) ? enabled.filter((p): p is string => typeof p === 'string') : null,
  );
  const providers: Record<string, boolean> = {};
  for (const p of PROVIDERS) {
    providers[p.key] = enabledSet.has(p.key) || (Array.isArray(enabled) ? false : DEFAULTS.providers[p.key] === true);
  }
  return {
    providers,
    scan_interval_minutes: asNumber(readDotted(cfg, 'library.scan_interval_minutes'), DEFAULTS.scan_interval_minutes),
    voice_model: asString(readDotted(cfg, 'voice.model'), DEFAULTS.voice_model),
    voice_device: ((): SettingsState['voice_device'] => {
      const v = asString(readDotted(cfg, 'voice.device'), DEFAULTS.voice_device);
      return v === 'auto' || v === 'cuda' || v === 'cpu' ? v : DEFAULTS.voice_device;
    })(),
    voice_mic_id: asString(readDotted(cfg, 'voice.mic_device_id'), DEFAULTS.voice_mic_id),
    voice_energy: asNumber(readDotted(cfg, 'voice.energy_threshold'), DEFAULTS.voice_energy),
    ctrl_deadzone: asNumber(readDotted(cfg, 'controller.deadzone'), DEFAULTS.ctrl_deadzone),
    ctrl_hold_ms: asNumber(readDotted(cfg, 'controller.hold_threshold_ms'), DEFAULTS.ctrl_hold_ms),
    ctrl_vibration: asBool(readDotted(cfg, 'controller.vibration_enabled'), DEFAULTS.ctrl_vibration),
    ctrl_voice_trigger: ((): SettingsState['ctrl_voice_trigger'] => {
      const v = asString(readDotted(cfg, 'controller.voice_trigger'), DEFAULTS.ctrl_voice_trigger);
      return v === 'rt' || v === 'lt' || v === 'hold_y' || v === 'hold_x' ? v : DEFAULTS.ctrl_voice_trigger;
    })(),
    rawg_key: asString(readDotted(cfg, 'services.rawg.api_key'), DEFAULTS.rawg_key),
    youtube_key: asString(readDotted(cfg, 'services.youtube.api_key'), DEFAULTS.youtube_key),
    twitch_connected: asString(readDotted(cfg, 'services.twitch.access_token'), '') !== '',
    autostart: asBool(readDotted(cfg, 'daemon.autostart'), DEFAULTS.autostart),
  };
}

function toPatch(s: SettingsState): ConfigMap {
  const providers = PROVIDERS.filter((p) => s.providers[p.key]).map((p) => p.key);
  return {
    library: {
      providers,
      scan_interval_minutes: Math.round(s.scan_interval_minutes),
    },
    voice: {
      model: s.voice_model,
      device: s.voice_device,
      mic_device_id: s.voice_mic_id,
      energy_threshold: s.voice_energy,
    },
    controller: {
      deadzone: s.ctrl_deadzone,
      hold_threshold_ms: Math.round(s.ctrl_hold_ms),
      vibration_enabled: s.ctrl_vibration,
      voice_trigger: s.ctrl_voice_trigger,
    },
    services: {
      rawg: { api_key: s.rawg_key.trim() },
      youtube: { api_key: s.youtube_key.trim() },
    },
    daemon: { autostart: s.autostart },
  };
}

// ── Page ─────────────────────────────────────────────────────────────

export function SettingsPage() {
  const [section, setSection] = useState<SectionKey>('library');
  const [state, setState] = useState<SettingsState>(DEFAULTS);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string>('');
  const [applyState, setApplyState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [applyError, setApplyError] = useState<string>('');
  const savedTimer = useRef<number | null>(null);

  // Load config once on mount.
  useEffect(() => {
    let cancelled = false;
    void invoke<ConfigMap>('config_get').then(
      (cfg) => {
        if (cancelled) return;
        setState(fromConfig(cfg ?? {}));
        setLoaded(true);
      },
      (err: unknown) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
        setLoaded(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (savedTimer.current !== null) {
        window.clearTimeout(savedTimer.current);
      }
    };
  }, []);

  const onApply = useCallback(async () => {
    setApplyState('saving');
    setApplyError('');
    try {
      await invoke('config_set', { patch: toPatch(state) });
      // Autostart toggle has its own dedicated command (also writes the
      // OS-level launch entry); fire it alongside the config write.
      try {
        await invoke('app_set_autostart', { enabled: state.autostart });
      } catch {
        /* autostart command may not be wired in this build — config still
         * captured the user's intent. */
      }
      setApplyState('saved');
      if (savedTimer.current !== null) window.clearTimeout(savedTimer.current);
      savedTimer.current = window.setTimeout(() => {
        setApplyState('idle');
        savedTimer.current = null;
      }, 2000);
    } catch (err: unknown) {
      setApplyError(err instanceof Error ? err.message : String(err));
      setApplyState('error');
    }
  }, [state]);

  const update = useCallback(<K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setState((s) => ({ ...s, [key]: value }));
  }, []);

  const applyLabel =
    applyState === 'saving' ? 'Saving…' : applyState === 'saved' ? 'Saved ✓' : 'Apply';

  return (
    <div className="settings fade-in">
      <aside className="settings__nav" aria-label="Settings sections">
        <p className="label settings__nav-head">SETTINGS</p>
        <ul className="settings__nav-list" role="tablist">
          {SECTIONS.map((s) => (
            <li key={s.key} role="presentation">
              <button
                type="button"
                className={`settings__nav-item label ${section === s.key ? 'settings__nav-item--active' : ''}`}
                onClick={() => setSection(s.key)}
                aria-selected={section === s.key}
                role="tab"
                data-focusable
              >
                {s.label}
              </button>
            </li>
          ))}
        </ul>
        <hr className="rule settings__nav-rule" />
        <div className="settings__apply-row">
          <button
            type="button"
            className="accent-btn settings__apply"
            onClick={onApply}
            disabled={applyState === 'saving' || !loaded}
            data-focusable
          >
            {applyLabel}
          </button>
          {applyError !== '' && (
            <p className="settings__apply-error" role="alert">
              {applyError}
            </p>
          )}
        </div>
      </aside>

      <main className="settings__panel">
        {!loaded ? (
          <p className="label settings__loading">LOADING…</p>
        ) : (
          <div className="settings__section fade-in" key={section}>
            {loadError !== '' && (
              <p className="settings__notice settings__notice--warn" role="alert">
                Couldn’t load saved config — showing defaults. {loadError}
              </p>
            )}
            {section === 'library' && (
              <LibrarySection state={state} update={update} />
            )}
            {section === 'voice' && (
              <VoiceSection state={state} update={update} />
            )}
            {section === 'controller' && (
              <ControllerSection state={state} update={update} />
            )}
            {section === 'services' && (
              <ServicesSection state={state} update={update} />
            )}
            {section === 'about' && (
              <AboutSection state={state} update={update} />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

// ── Section: Library ─────────────────────────────────────────────────

interface SectionProps {
  state: SettingsState;
  update: <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => void;
}

function LibrarySection({ state, update }: SectionProps) {
  const [scanState, setScanState] = useState<'idle' | 'scanning' | 'done' | 'error'>('idle');
  const [scanError, setScanError] = useState<string>('');
  const [scanLine, setScanLine] = useState<string>('');
  const [foundCount, setFoundCount] = useState<number>(0);

  // Subscribe to scan progress events. Emitted by future scanner work;
  // the panel quietly no-ops if no events come through.
  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    void listen<{ provider?: string; message?: string; count?: number }>(
      'library:scan:progress',
      (e) => {
        const p = e.payload ?? {};
        const line = p.message ?? (p.provider !== undefined ? `Scanning ${p.provider}…` : '');
        if (line !== '') setScanLine(line);
        if (typeof p.count === 'number') setFoundCount(p.count);
      },
    ).then((u) => {
      unlisten = u;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  const onScan = useCallback(async () => {
    setScanState('scanning');
    setScanError('');
    setScanLine('Starting scan…');
    setFoundCount(0);
    try {
      const games = await scanLibrary();
      setFoundCount(games.length);
      setScanLine(`Found ${games.length} ${games.length === 1 ? 'entry' : 'entries'}.`);
      setScanState('done');
    } catch (err: unknown) {
      setScanError(err instanceof Error ? err.message : String(err));
      setScanState('error');
    }
  }, []);

  return (
    <>
      <header className="settings__head">
        <p className="label">SECTION</p>
        <h2 className="settings__title display">Library</h2>
        <p className="settings__lede">
          Choose where Pixiis looks for games and how often it sweeps.
        </p>
      </header>

      <Field label="Providers" hint="Pixiis scans only the storefronts you check.">
        <div className="settings__checks">
          {PROVIDERS.map((p) => (
            <label key={p.key} className="settings__check" data-focusable>
              <input
                type="checkbox"
                checked={state.providers[p.key] === true}
                onChange={(e) =>
                  update('providers', { ...state.providers, [p.key]: e.target.checked })
                }
              />
              <span>{p.label}</span>
            </label>
          ))}
        </div>
      </Field>

      <Field label="Scan interval" hint="How often Pixiis re-scans in the background.">
        <div className="settings__slider-row">
          <input
            type="range"
            min={1}
            max={1440}
            step={1}
            value={state.scan_interval_minutes}
            onChange={(e) => update('scan_interval_minutes', Number(e.target.value))}
            data-focusable
            className="settings__slider"
          />
          <span className="settings__slider-value">
            {state.scan_interval_minutes} min
          </span>
        </div>
      </Field>

      <Field label="Scan now" hint="Trigger an immediate scan across enabled providers.">
        <div className="settings__scan">
          <button
            type="button"
            className="settings__btn"
            onClick={onScan}
            disabled={scanState === 'scanning'}
            data-focusable
          >
            {scanState === 'scanning' ? 'Scanning…' : 'Scan Now'}
          </button>
          {(scanState === 'scanning' || scanState === 'done') && scanLine !== '' && (
            <p className="settings__scan-line label">{scanLine.toUpperCase()}</p>
          )}
          {scanState === 'done' && foundCount > 0 && (
            <p className="settings__scan-count">
              {foundCount} {foundCount === 1 ? 'entry' : 'entries'} on file.
            </p>
          )}
          {scanState === 'error' && (
            <p className="settings__notice settings__notice--warn" role="alert">
              {scanError}
            </p>
          )}
        </div>
      </Field>
    </>
  );
}

// ── Section: Voice ───────────────────────────────────────────────────

function VoiceSection({ state, update }: SectionProps) {
  const [devices, setDevices] = useState<VoiceDevice[]>([]);
  const [devicesError, setDevicesError] = useState<string>('');

  // Voice test state (press-and-hold).
  const [testing, setTesting] = useState(false);
  const [partial, setPartial] = useState<string>('');
  const [finalText, setFinalText] = useState<string>('');
  const [voiceError, setVoiceError] = useState<string>('');

  // TTS test state.
  const [ttsState, setTtsState] = useState<'idle' | 'speaking' | 'pending' | 'error'>('idle');
  const [ttsError, setTtsError] = useState<string>('');

  // Load devices.
  useEffect(() => {
    let cancelled = false;
    void invoke<VoiceDevice[]>('voice_get_devices').then(
      (list) => {
        if (cancelled) return;
        setDevices(Array.isArray(list) ? list : []);
        // Pick a sensible default mic if user hasn't chosen one yet.
        if (state.voice_mic_id === '' && Array.isArray(list) && list.length > 0) {
          const def = list.find((d) => d.is_default) ?? list[0];
          if (def !== undefined) update('voice_mic_id', def.id);
        }
      },
      (err: unknown) => {
        if (cancelled) return;
        setDevicesError(err instanceof Error ? err.message : String(err));
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Subscribe to partial transcription events while testing.
  useEffect(() => {
    if (!testing) return;
    let unlistenPartial: UnlistenFn | undefined;
    let unlistenFinal: UnlistenFn | undefined;
    void listen<TranscriptionEvent>('voice:partial', (e) => {
      setPartial(e.payload.text);
    }).then((u) => {
      unlistenPartial = u;
    });
    void listen<TranscriptionEvent>('voice:final', (e) => {
      setFinalText(e.payload.text);
      setPartial('');
    }).then((u) => {
      unlistenFinal = u;
    });
    return () => {
      unlistenPartial?.();
      unlistenFinal?.();
    };
  }, [testing]);

  const startTest = useCallback(async () => {
    if (testing) return;
    setVoiceError('');
    setPartial('');
    setFinalText('');
    setTesting(true);
    try {
      await voiceStart();
    } catch (err: unknown) {
      setVoiceError(err instanceof Error ? err.message : String(err));
      setTesting(false);
    }
  }, [testing]);

  const stopTest = useCallback(async () => {
    if (!testing) return;
    setTesting(false);
    try {
      const result = await invoke<TranscriptionEvent | string>('voice_stop');
      const text = typeof result === 'string' ? result : (result?.text ?? '');
      if (text !== '') setFinalText(text);
    } catch (err: unknown) {
      setVoiceError(err instanceof Error ? err.message : String(err));
    }
  }, [testing]);

  const speakTest = useCallback(async () => {
    setTtsError('');
    setTtsState('speaking');
    try {
      await invoke('voice_speak', { text: 'This is the Pixiis voice.' });
      setTtsState('idle');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      // Command isn't wired yet — surface the soft-dep affordance.
      if (/not implemented|unknown|no such/i.test(msg)) {
        setTtsState('pending');
      } else {
        setTtsError(msg);
        setTtsState('error');
      }
    }
  }, []);

  return (
    <>
      <header className="settings__head">
        <p className="label">SECTION</p>
        <h2 className="settings__title display">Voice</h2>
        <p className="settings__lede">
          Whisper for transcription. Hold the test button and speak.
        </p>
      </header>

      <Field label="Whisper model" hint="Larger = more accurate, slower to load.">
        <select
          className="settings__select"
          value={state.voice_model}
          onChange={(e) => update('voice_model', e.target.value)}
          data-focusable
        >
          {VOICE_MODELS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Compute device" hint="‘auto’ uses CUDA when available, else CPU.">
        <select
          className="settings__select"
          value={state.voice_device}
          onChange={(e) =>
            update('voice_device', e.target.value as SettingsState['voice_device'])
          }
          data-focusable
        >
          {VOICE_DEVICES.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Microphone" hint="Audio source for live transcription.">
        {devices.length === 0 ? (
          <p className="settings__hint">
            {devicesError !== '' ? devicesError : 'Pending wave2/voice merge.'}
          </p>
        ) : (
          <select
            className="settings__select"
            value={state.voice_mic_id}
            onChange={(e) => update('voice_mic_id', e.target.value)}
            data-focusable
          >
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
                {d.is_default ? ' — default' : ''}
              </option>
            ))}
          </select>
        )}
      </Field>

      <Field label="Energy threshold" hint="Below this RMS, audio is treated as silence.">
        <div className="settings__slider-row">
          <input
            type="range"
            min={50}
            max={1000}
            step={10}
            value={state.voice_energy}
            onChange={(e) => update('voice_energy', Number(e.target.value))}
            data-focusable
            className="settings__slider"
          />
          <span className="settings__slider-value">{Math.round(state.voice_energy)}</span>
        </div>
      </Field>

      <Field label="Test voice" hint="Press and hold; release to finalise.">
        <div className="settings__voice-test">
          <button
            type="button"
            className={`settings__btn ${testing ? 'settings__btn--active' : ''}`}
            onPointerDown={startTest}
            onPointerUp={stopTest}
            onPointerLeave={() => {
              if (testing) void stopTest();
            }}
            data-focusable
          >
            {testing ? 'Listening…' : 'Hold to test'}
          </button>
          <div className="settings__voice-readout" aria-live="polite">
            {partial !== '' && (
              <p className="settings__voice-partial label">{partial}</p>
            )}
            {finalText !== '' && (
              <p className="settings__voice-final">{finalText}</p>
            )}
            {partial === '' && finalText === '' && !testing && (
              <p className="settings__hint">
                {voiceError !== '' ? voiceError : 'Awaiting input.'}
              </p>
            )}
          </div>
        </div>
      </Field>

      <Field label="Test TTS" hint="Speak a short sample with the bundled voice.">
        <div className="settings__tts-test">
          <button
            type="button"
            className="settings__btn"
            onClick={speakTest}
            disabled={ttsState === 'speaking'}
            data-focusable
          >
            {ttsState === 'speaking' ? 'Speaking…' : 'Test TTS'}
          </button>
          {ttsState === 'pending' && (
            <p className="settings__hint">Pending wave2/tts merge.</p>
          )}
          {ttsState === 'error' && (
            <p className="settings__notice settings__notice--warn" role="alert">
              {ttsError}
            </p>
          )}
        </div>
      </Field>
    </>
  );
}

// ── Section: Controller ──────────────────────────────────────────────

function ControllerSection({ state, update }: SectionProps) {
  const [ctrl, setCtrl] = useState<ControllerState | null>(null);

  // Poll controller state at 1 Hz while the section is mounted.
  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;
    const tick = (): void => {
      void invoke<ControllerState>('controller_get_state').then(
        (s) => {
          if (cancelled) return;
          setCtrl(s);
        },
        () => {
          /* shape may not be wired yet — treat as disconnected */
          if (cancelled) return;
          setCtrl(null);
        },
      );
    };
    tick();
    timer = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearInterval(timer);
    };
  }, []);

  return (
    <>
      <header className="settings__head">
        <p className="label">SECTION</p>
        <h2 className="settings__title display">Controller</h2>
        <p className="settings__lede">
          Tune deadzones and how Pixiis listens for the voice trigger.
        </p>
      </header>

      <Field label="Status" hint="Detected via the gilrs background poller.">
        <p className="settings__status">
          <span
            className={`settings__status-dot settings__status-dot--${
              ctrl?.connected === true ? 'on' : 'off'
            }`}
            aria-hidden="true"
          />
          <span className="settings__status-text">
            {ctrl?.connected === true ? 'Connected' : 'No controller detected'}
          </span>
        </p>
      </Field>

      <Field label="Deadzone" hint="Stick travel ignored before motion registers.">
        <div className="settings__slider-row">
          <input
            type="range"
            min={0}
            max={50}
            step={1}
            value={Math.round(state.ctrl_deadzone * 100)}
            onChange={(e) => update('ctrl_deadzone', Number(e.target.value) / 100)}
            data-focusable
            className="settings__slider"
          />
          <span className="settings__slider-value">{state.ctrl_deadzone.toFixed(2)}</span>
        </div>
      </Field>

      <Field label="Hold threshold" hint="How long a button must stay down to count as ‘held’.">
        <div className="settings__slider-row">
          <input
            type="range"
            min={100}
            max={500}
            step={10}
            value={Math.round(state.ctrl_hold_ms)}
            onChange={(e) => update('ctrl_hold_ms', Number(e.target.value))}
            data-focusable
            className="settings__slider"
          />
          <span className="settings__slider-value">{Math.round(state.ctrl_hold_ms)} ms</span>
        </div>
      </Field>

      <Field label="Vibration" hint="Rumble on macro fire and selection events.">
        <label className="settings__check" data-focusable>
          <input
            type="checkbox"
            checked={state.ctrl_vibration}
            onChange={(e) => update('ctrl_vibration', e.target.checked)}
          />
          <span>Enabled</span>
        </label>
      </Field>

      <Field label="Voice trigger" hint="Which controller input opens the voice prompt.">
        <select
          className="settings__select"
          value={state.ctrl_voice_trigger}
          onChange={(e) =>
            update('ctrl_voice_trigger', e.target.value as SettingsState['ctrl_voice_trigger'])
          }
          data-focusable
        >
          {VOICE_TRIGGERS.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </Field>
    </>
  );
}

// ── Section: Services ────────────────────────────────────────────────

function ServicesSection({ state, update }: SectionProps) {
  // The persisted side of Twitch comes from `state.twitch_connected`.
  // `oauthOp` tracks the in-flight OAuth attempt; the displayed status is
  // derived from both so we never duplicate truth.
  const [oauthOp, setOauthOp] = useState<'idle' | 'connecting' | 'error'>('idle');
  const [twitchError, setTwitchError] = useState<string>('');
  const twitchState: 'idle' | 'connecting' | 'connected' | 'error' =
    oauthOp === 'connecting'
      ? 'connecting'
      : oauthOp === 'error'
        ? 'error'
        : state.twitch_connected
          ? 'connected'
          : 'idle';

  const connectTwitch = useCallback(async () => {
    setOauthOp('connecting');
    setTwitchError('');
    try {
      await invoke('services_oauth_start', { provider: 'twitch' });
      // The OAuth flow finishes in a browser tab; the backend writes the
      // token into the config when the redirect lands. Re-load on next
      // Apply / page revisit.
      setOauthOp('idle');
    } catch (err: unknown) {
      setTwitchError(err instanceof Error ? err.message : String(err));
      setOauthOp('error');
    }
  }, []);

  const twitchLabel =
    twitchState === 'connecting'
      ? 'Check your browser'
      : twitchState === 'connected'
        ? 'Connected'
        : twitchState === 'error'
          ? 'Failed'
          : 'Not connected';

  return (
    <>
      <header className="settings__head">
        <p className="label">SECTION</p>
        <h2 className="settings__title display">Services</h2>
        <p className="settings__lede">
          API keys for the metadata, video, and stream feeds.
        </p>
      </header>

      <Field label="RAWG API key" hint="Powers descriptions, screenshots, genres, scores.">
        <input
          type="password"
          className="settings__input"
          value={state.rawg_key}
          onChange={(e) => update('rawg_key', e.target.value)}
          placeholder="rawg-…"
          data-focusable
          spellCheck={false}
          autoComplete="off"
        />
      </Field>

      <Field label="YouTube API key" hint="Used for trailer lookups on the detail page.">
        <input
          type="password"
          className="settings__input"
          value={state.youtube_key}
          onChange={(e) => update('youtube_key', e.target.value)}
          placeholder="AIza…"
          data-focusable
          spellCheck={false}
          autoComplete="off"
        />
      </Field>

      <Field label="Twitch" hint="OAuth completes in your browser.">
        <div className="settings__twitch">
          <button
            type="button"
            className="settings__btn"
            onClick={connectTwitch}
            disabled={twitchState === 'connecting'}
            data-focusable
          >
            {twitchState === 'connected' ? 'Reconnect with Twitch' : 'Connect with Twitch'}
          </button>
          <span
            className={`settings__twitch-status settings__twitch-status--${twitchState}`}
            role="status"
          >
            {twitchLabel}
          </span>
          {twitchError !== '' && (
            <p className="settings__notice settings__notice--warn" role="alert">
              {twitchError}
            </p>
          )}
        </div>
      </Field>
    </>
  );
}

// ── Section: About ───────────────────────────────────────────────────

const APP_VERSION = '0.1.0';
const LICENSE = 'MIT';
const REPO_URL = 'https://github.com/anthropics/pixiis';

function AboutSection({ state, update }: SectionProps) {
  return (
    <>
      <header className="settings__head">
        <p className="label">SECTION</p>
        <h2 className="settings__title display">About</h2>
        <p className="settings__lede">An editorial launcher. Quiet, framed, restrained.</p>
      </header>

      <Field label="Version" hint="The shipped Tauri build.">
        <p className="settings__static">Pixiis · {APP_VERSION}</p>
      </Field>

      <Field label="License" hint="Source available under the project license.">
        <p className="settings__static">{LICENSE}</p>
      </Field>

      <Field label="Source" hint="Issues, releases, and the full changelog.">
        <a
          href={REPO_URL}
          target="_blank"
          rel="noreferrer noopener"
          className="settings__link"
          data-focusable
        >
          {REPO_URL}
        </a>
      </Field>

      <Field label="Start with Windows" hint="Launch Pixiis quietly to the system tray on login.">
        <label className="settings__check" data-focusable>
          <input
            type="checkbox"
            checked={state.autostart}
            onChange={(e) => update('autostart', e.target.checked)}
          />
          <span>Autostart</span>
        </label>
      </Field>
    </>
  );
}

// ── Field row ────────────────────────────────────────────────────────

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="settings__field">
      <div className="settings__field-meta">
        <p className="label settings__field-label">{label.toUpperCase()}</p>
        {hint !== undefined && <p className="settings__field-hint">{hint}</p>}
      </div>
      <div className="settings__field-control">{children}</div>
    </section>
  );
}
