"""Voice pipeline orchestrator — replaces shout.py's global state."""

from __future__ import annotations

import queue
import threading
import time

import numpy as np

from pixiis.core.config import get_config
from pixiis.core.events import bus
from pixiis.core.types import ActionType, MacroAction, TranscriptionEvent
from pixiis.voice.audio_capture import AudioCapture
from pixiis.voice.text_injection import TextInjector
from pixiis.voice.transcriber import Transcriber
from pixiis.voice.vad import VADBackend, get_vad


class VoicePipeline:
    """Central orchestrator wiring audio capture, VAD, transcription,
    TTS, and text injection together.

    Subscribes to :class:`MacroAction` events with
    ``action == ActionType.VOICE_RECORD`` on the global event bus.
    A *hold-start* event begins recording + rolling live transcription;
    a *hold-stop* event triggers a final high-quality transcription and
    injects the result into the focused window.
    """

    # ── rolling-transcription tuning (from shout.py) ─────────────────
    CHUNK_SIZE = 64
    VAD_SILENCE_WAIT = 0.5       # seconds of silence before cutting
    MIN_SPEECH_SECONDS = 0.75    # minimum speech before transcribing
    MAX_LIVE_SECONDS = 5.0       # force cut after this many seconds
    MAX_DEDUP_HISTORY = 10

    def __init__(self) -> None:
        cfg = get_config()

        self.sample_rate: int = cfg.get("voice.sample_rate", 16000)
        self.energy_threshold: float = cfg.get("voice.energy_threshold", 300.0)
        self.CHUNK_SIZE = cfg.get("voice.chunk_size", self.CHUNK_SIZE)

        # ── sub-components ───────────────────────────────────────────
        self._capture = AudioCapture(
            sample_rate=self.sample_rate,
            chunk_size=self.CHUNK_SIZE,
        )
        self._transcriber = Transcriber(
            output_file="transcription.txt",
            sample_rate=self.sample_rate,
        )
        self._injector = TextInjector()
        self._vad: VADBackend = get_vad(cfg.get("voice.vad_backend", "silero"))

        # ── models (lazy-loaded) ─────────────────────────────────────
        self._live_model_name: str = cfg.get("voice.live_model", "large-v3")
        self._final_model_name: str = cfg.get("voice.final_model", "large-v3")
        self._device: str = cfg.get("voice.device", "cuda")
        self._live_model = None
        self._final_model = None

        # ── TTS (optional) ───────────────────────────────────────────
        self._tts = None
        if cfg.get("voice.tts.enabled", True):
            try:
                from pixiis.voice.tts import TTSEngine
                self._tts = TTSEngine()
            except Exception:
                pass

        # ── internal state ───────────────────────────────────────────
        self._transcription_queue: queue.Queue = queue.Queue()
        self._tts_queue: queue.Queue = queue.Queue()
        self._shutdown_event = threading.Event()

        self._last_transcribed_index = 0
        self._live_line_count = 0
        self._live_line_lock = threading.Lock()

        # deduplication
        self._dedup_history: list[str] = []
        self._dedup_lock = threading.Lock()

        # threads
        self._threads: list[threading.Thread] = []

    # ── model loading ────────────────────────────────────────────────

    def _ensure_models(self) -> None:
        """Load Whisper models. Checks for bundled model first, then downloads."""
        if self._live_model is not None:
            return

        compute = "float16" if self._device == "cuda" else "int8"

        # Check for bundled model (PyInstaller distribution)
        model_name = self._live_model_name
        bundled = self._find_bundled_model(model_name)
        if bundled is not None:
            model_name = str(bundled)
            print(f"Using bundled Whisper model: {bundled}")
        else:
            print(f"Loading Whisper model ({model_name})...")

        self._live_model = self._transcriber.load_model(
            model_name, device=self._device, compute_type=compute,
        )

        if self._final_model_name == self._live_model_name:
            self._final_model = self._live_model
        else:
            final_name = self._final_model_name
            bundled_final = self._find_bundled_model(final_name)
            if bundled_final is not None:
                final_name = str(bundled_final)
            self._final_model = self._transcriber.load_model(
                final_name, device=self._device, compute_type=compute,
            )

    @staticmethod
    def _find_bundled_model(name: str) -> Path | None:
        """Check if a Whisper model is bundled with the app."""
        import sys
        # PyInstaller sets sys._MEIPASS to the temp extraction dir
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent.parent.parent))
        candidates = [
            base / "models" / f"whisper-{name}",
            base / "models" / name,
        ]
        for p in candidates:
            if p.exists() and any(p.iterdir()):
                return p
        return None

    # ── lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        """Subscribe to events and spin up worker threads."""
        bus.subscribe(MacroAction, self._on_macro_action)

        workers = [
            ("transcription-worker", self._transcription_worker),
            ("rolling-transcribe", self._rolling_transcribe_loop),
        ]
        if self._tts is not None:
            workers.append(("tts-worker", self._tts_worker))

        for name, target in workers:
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        """Shut everything down cleanly."""
        self._shutdown_event.set()
        # Unblock rolling loop if waiting on recording_event
        self._capture.recording_event.set()
        self._capture.stop()
        bus.unsubscribe(MacroAction, self._on_macro_action)
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()

    # ── event handling ───────────────────────────────────────────────

    def _on_macro_action(self, action: MacroAction) -> None:
        if action.action is not ActionType.VOICE_RECORD:
            return

        if action.target == "start":
            self._start_recording()
        elif action.target == "stop":
            self._stop_recording()

    def _start_recording(self) -> None:
        self._ensure_models()
        self._capture.clear_buffer()
        self._last_transcribed_index = 0
        with self._live_line_lock:
            self._live_line_count = 0
        self._capture.start()
        print("  [recording...]")

    def _stop_recording(self) -> None:
        self._capture.recording_event.clear()
        time.sleep(0.05)  # let last chunks arrive

        full_buffer = self._capture.get_buffer()
        self._capture.stop()

        if full_buffer:
            self._transcription_queue.put(
                (full_buffer, "[final] ", self._final_model, True)
            )

    # ── deduplication ────────────────────────────────────────────────

    def _is_duplicate(self, text: str) -> bool:
        if not text:
            return False
        with self._dedup_lock:
            return any(text.strip() == prev.strip() for prev in self._dedup_history)

    def _add_to_history(self, text: str) -> None:
        if text:
            with self._dedup_lock:
                self._dedup_history.append(text)
                self._dedup_history[:] = self._dedup_history[-self.MAX_DEDUP_HISTORY:]

    # ── energy gate ──────────────────────────────────────────────────

    def _passes_energy_gate(self, chunk: np.ndarray) -> bool:
        if self.energy_threshold <= 0:
            return True
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        return rms >= self.energy_threshold

    # ── transcription worker ─────────────────────────────────────────

    def _transcription_worker(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                buffer_copy, label, model, is_final = self._transcription_queue.get(
                    timeout=0.5
                )
            except queue.Empty:
                continue

            try:
                start = time.time()
                text = self._transcriber.transcribe_buffer(
                    buffer_copy, model, prompt="", fast=not is_final,
                )
                elapsed = time.time() - start

                if not text:
                    continue

                if is_final:
                    print(f"{label}>> {text}  [{elapsed:.2f}s]")
                    with self._live_line_lock:
                        live_count = self._live_line_count
                        self._live_line_count = 0
                    self._transcriber.replace_live_with_final(
                        text, live_count=live_count,
                    )
                    self._add_to_history(text)
                    # Don't inject via SendInput or speak via TTS —
                    # the UI handles text placement via TranscriptionEvent
                    bus.publish(TranscriptionEvent(
                        text=text, is_final=True, timestamp=time.time(),
                    ))
                    print()
                else:
                    if self._is_duplicate(text):
                        print(f"{label}[DEDUP] {text}")
                    else:
                        print(f"{label}>> {text}  [{elapsed:.2f}s]")
                        self._transcriber.write_line(text)
                        self._add_to_history(text)
                        bus.publish(TranscriptionEvent(
                            text=text, is_final=False, timestamp=time.time(),
                        ))
                        with self._live_line_lock:
                            self._live_line_count += 1

            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                self._transcription_queue.task_done()

    # ── rolling transcription loop ───────────────────────────────────

    def _rolling_transcribe_loop(self) -> None:
        """VAD-based streaming: segment speech in real time and queue
        live transcriptions.  Mirrors shout.py lines 217-280."""
        recording_event = self._capture.recording_event

        while not self._shutdown_event.is_set():
            recording_event.wait(timeout=0.5)
            if self._shutdown_event.is_set():
                break
            if not recording_event.is_set():
                continue

            self._last_transcribed_index = 0
            last_had_speech = False

            while recording_event.is_set() and not self._shutdown_event.is_set():
                time.sleep(0.1)
                if not recording_event.is_set():
                    break

                with self._capture._lock:
                    current_index = len(self._capture._buffer)
                    new_chunk_count = current_index - self._last_transcribed_index

                if new_chunk_count <= 0:
                    continue

                elapsed_seconds = new_chunk_count * self.CHUNK_SIZE / self.sample_rate

                if elapsed_seconds < self.MIN_SPEECH_SECONDS:
                    continue

                force_cut = elapsed_seconds >= self.MAX_LIVE_SECONDS

                if not force_cut:
                    silence_check_chunks = int(
                        self.sample_rate * self.VAD_SILENCE_WAIT / self.CHUNK_SIZE
                    )
                    with self._capture._lock:
                        start = max(0, current_index - silence_check_chunks)
                        recent = self._capture._buffer[start:current_index]

                    if not recent:
                        continue

                    all_silent = all(
                        not self._passes_energy_gate(c) or not self._vad.is_speech(c, self.sample_rate)
                        for c in recent
                    )

                    if not all_silent:
                        last_had_speech = True
                        continue

                    if not last_had_speech:
                        continue

                # Grab chunks with overlap for context (shout.py lines 269-272)
                overlap_chunks = int(self.sample_rate * 0.5 / self.CHUNK_SIZE)
                with self._capture._lock:
                    overlap_start = max(
                        0, self._last_transcribed_index - overlap_chunks,
                    )
                    new_chunks = list(
                        self._capture._buffer[overlap_start:current_index]
                    )

                min_chunks = int(
                    self.sample_rate * self.MIN_SPEECH_SECONDS / self.CHUNK_SIZE
                )
                if len(new_chunks) < min_chunks:
                    continue

                self._last_transcribed_index = current_index
                last_had_speech = False
                self._transcription_queue.put(
                    (new_chunks, "[live] ", self._live_model, False)
                )

    # ── TTS worker ───────────────────────────────────────────────────

    def _tts_worker(self) -> None:
        while not self._shutdown_event.is_set():
            try:
                text = self._tts_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if self._tts is not None:
                    self._tts.speak(text)
            except Exception as e:
                print(f"TTS error: {e}")
