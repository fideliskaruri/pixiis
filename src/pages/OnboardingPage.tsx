/**
 * OnboardingPage — First-launch editorial walkthrough.
 *
 * Five steps, single-column, generous whitespace. Each step is its own
 * component so the cross-fade on advance is a simple key swap. The
 * marker file (%APPDATA%/pixiis/.onboarded) is written via
 * `app_set_onboarded` on completion or skip.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { scanLibrary, setOnboarded } from '../api/bridge';
import { ScanProgress } from '../components/ScanProgress';
import {
  applyProgressEvent,
  initialProviderRows,
  type ProviderRow,
} from '../components/scanProgressState';
import { useController, type ControllerButton } from '../hooks/useController';
import './OnboardingPage.css';

const TOTAL_STEPS = 5;

type StepIndex = 0 | 1 | 2 | 3 | 4;

export function OnboardingPage() {
  const [step, setStep] = useState<StepIndex>(0);
  const [exiting, setExiting] = useState(false);
  const navigate = useNavigate();

  const advance = useCallback(() => {
    setStep((s) => (s < (TOTAL_STEPS - 1) ? ((s + 1) as StepIndex) : s));
  }, []);

  const finish = useCallback(
    async (markComplete: boolean) => {
      if (exiting) return;
      setExiting(true);
      try {
        if (markComplete) await setOnboarded(true);
        else await setOnboarded(true); // skip also marks the user as onboarded
      } catch {
        // Marker write failed — still navigate so the user isn't stuck;
        // they'll just see onboarding again on next launch.
      }
      navigate('/', { replace: true });
    },
    [exiting, navigate],
  );

  return (
    <div className="onboarding">
      <button
        type="button"
        className="onboarding__skip"
        onClick={() => void finish(false)}
        data-focusable
        aria-label="Skip setup"
      >
        Skip setup
      </button>

      <div className="onboarding__stage" key={step}>
        {step === 0 && <WelcomeStep onNext={advance} />}
        {step === 1 && <LibraryScanStep onNext={advance} />}
        {step === 2 && <VoiceMicStep onNext={advance} />}
        {step === 3 && <ControllerStep onNext={advance} />}
        {step === 4 && <DoneStep onFinish={() => void finish(true)} />}
      </div>

      <p className="onboarding__indicator label">
        STEP {step + 1} / {TOTAL_STEPS}
      </p>
    </div>
  );
}

// ── Step 1 · Welcome ──────────────────────────────────────────────────

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <StepShell>
      <p className="label onboarding__eyebrow">A LAUNCHER</p>
      <h1 className="display onboarding__title">Pixiis</h1>
      <p className="onboarding__lede">Your games, one launcher.</p>
      <div className="onboarding__cta-row">
        <button
          type="button"
          className="onboarding__primary"
          onClick={onNext}
          data-focusable
          autoFocus
        >
          Begin
        </button>
      </div>
    </StepShell>
  );
}

// ── Step 2 · Library scan ─────────────────────────────────────────────

interface ScanProgressEvent {
  provider?: string;
  state?: string;
  count?: number;
  error?: string;
}

function LibraryScanStep({ onNext }: { onNext: () => void }) {
  const [rows, setRows] = useState<ProviderRow[]>(initialProviderRows);
  const [done, setDone] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    let unlisten: UnlistenFn | null = null;
    let cancelled = false;

    void (async () => {
      try {
        unlisten = await listen<ScanProgressEvent>(
          'library:scan:progress',
          (event) => {
            setRows((current) => applyProgressEvent(current, event.payload ?? {}));
          },
        );
      } catch {
        // Event channel unavailable in the current build — fall back
        // to the post-scan summary derived from the entry list.
      }

      // Mark every provider as scanning while we wait for either the
      // progress events or the scan() Promise to resolve.
      setRows((current) =>
        current.map((r) => ({ ...r, state: 'scanning' as const })),
      );

      try {
        const games = await scanLibrary();
        if (cancelled) return;
        const counts = new Map<string, number>();
        for (const g of games) {
          counts.set(g.source, (counts.get(g.source) ?? 0) + 1);
        }
        setRows((current) =>
          current.map((r) => {
            // Keep any explicit per-provider events the backend sent;
            // for rows still in `scanning`, derive done/unavailable from
            // the count we observed in the result list.
            if (r.state === 'done' || r.state === 'error') return r;
            const c = counts.get(r.key) ?? 0;
            return c > 0
              ? { ...r, state: 'done', count: c }
              : { ...r, state: 'unavailable', count: 0 };
          }),
        );
        setDone(true);
      } catch (err) {
        if (cancelled) return;
        setScanError(err instanceof Error ? err.message : String(err));
        setDone(true);
      }
    })();

    return () => {
      cancelled = true;
      if (unlisten !== null) unlisten();
    };
  }, []);

  const totalGames = useMemo(
    () => rows.reduce((sum, r) => sum + (r.state === 'done' ? r.count : 0), 0),
    [rows],
  );

  return (
    <StepShell>
      <p className="label onboarding__eyebrow">SETUP · ONE OF FOUR</p>
      <h2 className="display onboarding__title onboarding__title--small">
        Finding your games.
      </h2>
      <p className="onboarding__lede">
        Pixiis looks through your stores and a few common folders. This takes a
        moment.
      </p>

      <ScanProgress rows={rows} scanning={!done} />

      <div className="onboarding__cta-row">
        <p className="onboarding__count">
          {scanError !== null
            ? `Could not scan: ${scanError}`
            : done
              ? `${totalGames} ${totalGames === 1 ? 'game' : 'games'} found.`
              : 'Scanning…'}
        </p>
        <button
          type="button"
          className="onboarding__primary"
          onClick={onNext}
          disabled={!done}
          data-focusable
        >
          Continue
        </button>
      </div>
    </StepShell>
  );
}

// ── Step 3 · Voice mic test ───────────────────────────────────────────

function VoiceMicStep({ onNext }: { onNext: () => void }) {
  const [holding, setHolding] = useState(false);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [hasSpoken, setHasSpoken] = useState(false);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number>(0);

  const stop = useCallback(() => {
    if (rafRef.current !== 0) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void ctxRef.current?.close().catch(() => {});
    ctxRef.current = null;
    setLevel(0);
  }, []);

  useEffect(() => () => stop(), [stop]);

  const start = useCallback(async () => {
    if (streamRef.current !== null) return;
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      const buffer = new Float32Array(analyser.fftSize);

      const tick = (): void => {
        analyser.getFloatTimeDomainData(buffer);
        let sumSq = 0;
        for (let i = 0; i < buffer.length; i += 1) {
          sumSq += buffer[i]! * buffer[i]!;
        }
        const rms = Math.sqrt(sumSq / buffer.length);
        // Map 0..0.4 RMS to 0..1, clamp.
        const next = Math.min(1, rms * 2.5);
        setLevel(next);
        if (next > 0.12) setHasSpoken(true);
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Microphone access was denied or unavailable.',
      );
      stop();
    }
  }, [stop]);

  const onPress = useCallback(() => {
    setHolding(true);
    void start();
  }, [start]);

  const onRelease = useCallback(() => {
    setHolding(false);
    stop();
  }, [stop]);

  return (
    <StepShell>
      <p className="label onboarding__eyebrow">SETUP · TWO OF FOUR</p>
      <h2 className="display onboarding__title onboarding__title--small">
        Say something.
      </h2>
      <p className="onboarding__lede">
        Hold the button below and read this out: <em>“Open Hades.”</em> The
        meter should move with your voice.
      </p>

      <div className="onboarding__meter" aria-hidden>
        <div className="onboarding__meter-track">
          <div
            className="onboarding__meter-fill"
            style={{ width: `${Math.round(level * 100)}%` }}
          />
        </div>
      </div>

      {error !== null && (
        <p className="onboarding__error" role="alert">
          {error}
        </p>
      )}

      <div className="onboarding__cta-row">
        <button
          type="button"
          className={`onboarding__hold ${holding ? 'onboarding__hold--active' : ''}`}
          onMouseDown={onPress}
          onMouseUp={onRelease}
          onMouseLeave={holding ? onRelease : undefined}
          onTouchStart={onPress}
          onTouchEnd={onRelease}
          data-focusable
        >
          {holding ? 'Listening…' : 'Hold to speak'}
        </button>
        <button
          type="button"
          className="onboarding__primary"
          onClick={onNext}
          disabled={!hasSpoken && error === null}
          data-focusable
        >
          {hasSpoken || error !== null ? 'Continue' : 'Speak first'}
        </button>
      </div>
    </StepShell>
  );
}

// ── Step 4 · Controller test ─────────────────────────────────────────

const GLYPH_BUTTONS: { key: ControllerButton; label: string; pos: string }[] = [
  { key: 'y', label: 'Y', pos: 'top' },
  { key: 'x', label: 'X', pos: 'left' },
  { key: 'b', label: 'B', pos: 'right' },
  { key: 'a', label: 'A', pos: 'bottom' },
];

function ControllerStep({ onNext }: { onNext: () => void }) {
  const [pressed, setPressed] = useState<Set<ControllerButton>>(
    () => new Set(),
  );
  const [anyPress, setAnyPress] = useState(false);

  const onButton = useCallback((b: ControllerButton) => {
    setAnyPress(true);
    setPressed((prev) => {
      const next = new Set(prev);
      next.add(b);
      return next;
    });
    window.setTimeout(() => {
      setPressed((prev) => {
        const next = new Set(prev);
        next.delete(b);
        return next;
      });
    }, 320);
  }, []);

  useController(onButton);

  return (
    <StepShell>
      <p className="label onboarding__eyebrow">SETUP · THREE OF FOUR</p>
      <h2 className="display onboarding__title onboarding__title--small">
        Press any button.
      </h2>
      <p className="onboarding__lede">
        Pixiis is built for a controller. We’ll light up the matching face
        button so you know it’s working.
      </p>

      <div className="onboarding__pad" aria-hidden>
        <div className="onboarding__pad-cluster">
          {GLYPH_BUTTONS.map((g) => (
            <span
              key={g.key}
              className={`onboarding__pad-btn onboarding__pad-btn--${g.pos} ${
                pressed.has(g.key) ? 'onboarding__pad-btn--lit' : ''
              }`}
            >
              {g.label}
            </span>
          ))}
        </div>
      </div>

      <p className="onboarding__hint label">
        {anyPress ? 'GOT IT' : 'WAITING FOR INPUT'}
      </p>

      <div className="onboarding__cta-row">
        <button
          type="button"
          className="onboarding__ghost"
          onClick={onNext}
          data-focusable
        >
          No controller right now
        </button>
        <button
          type="button"
          className="onboarding__primary"
          onClick={onNext}
          disabled={!anyPress}
          data-focusable
        >
          Looks good
        </button>
      </div>
    </StepShell>
  );
}

// ── Step 5 · Done ────────────────────────────────────────────────────

function DoneStep({ onFinish }: { onFinish: () => void }) {
  return (
    <StepShell>
      <p className="label onboarding__eyebrow">READY</p>
      <h2 className="display onboarding__title">You’re ready.</h2>
      <p className="onboarding__lede">
        Hit the button. Your library opens up.
      </p>
      <div className="onboarding__cta-row">
        <button
          type="button"
          className="onboarding__primary onboarding__primary--accent"
          onClick={onFinish}
          data-focusable
          autoFocus
        >
          Open Pixiis
        </button>
      </div>
    </StepShell>
  );
}

// ── Layout primitive ──────────────────────────────────────────────────

function StepShell({ children }: { children: ReactNode }) {
  return <div className="onboarding__step fade-in">{children}</div>;
}
