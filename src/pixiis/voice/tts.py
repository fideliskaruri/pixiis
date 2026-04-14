"""Text-to-speech engine wrapping Kokoro ONNX."""

from __future__ import annotations

import os
import threading
import urllib.request
from typing import TYPE_CHECKING

from pixiis.core.config import get_config

if TYPE_CHECKING:
    from kokoro_onnx import Kokoro

# ── model URLs ───────────────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.expanduser("~"), ".cache", "kokoro")
ONNX_PATH = os.path.join(MODELS_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODELS_DIR, "voices-v1.0.bin")
KOKORO_ONNX_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"


def _download_file(url: str, dest: str) -> None:
    """Download a file with progress reporting."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"Downloading {os.path.basename(dest)}...")

    def _progress(count: int, block_size: int, total_size: int) -> None:
        percent = min(int(count * block_size * 100 / total_size), 100)
        print(f"\r  {percent}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=_progress)
    print()


class TTSEngine:
    """Kokoro-based text-to-speech with auto-download and async playback.

    Usage:
        tts = TTSEngine()
        tts.speak("Hello world")       # blocking
        tts.speak_async("Hello world")  # fire-and-forget
    """

    def __init__(
        self,
        voice: str | None = None,
        speed: float | None = None,
    ) -> None:
        cfg = get_config()
        self.voice = voice or cfg.get("voice.tts.voice", "am_michael")
        self.speed = speed or cfg.get("voice.tts.speed", 1.0)
        self._kokoro: Kokoro | None = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> Kokoro:
        """Lazy-load the Kokoro model, downloading weights if needed."""
        if self._kokoro is not None:
            return self._kokoro

        try:
            from kokoro_onnx import Kokoro
        except ImportError:
            raise RuntimeError(
                "kokoro-onnx is required for TTS. Install with: pip install kokoro-onnx"
            )

        if not os.path.exists(ONNX_PATH):
            _download_file(KOKORO_ONNX_URL, ONNX_PATH)
        if not os.path.exists(VOICES_PATH):
            _download_file(KOKORO_VOICES_URL, VOICES_PATH)

        self._kokoro = Kokoro(ONNX_PATH, VOICES_PATH)
        return self._kokoro

    def speak(self, text: str) -> None:
        """Generate speech and play it synchronously via sounddevice."""
        if not text:
            return

        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError(
                "sounddevice is required for TTS playback. Install with: pip install sounddevice"
            )

        kokoro = self._ensure_model()

        with self._lock:
            samples, sample_rate = kokoro.create(
                text, voice=self.voice, speed=self.speed, lang="en-us"
            )

        sd.play(samples, samplerate=sample_rate)
        sd.wait()

    def speak_async(self, text: str) -> threading.Thread:
        """Run speak() in a background thread. Returns the thread handle."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()
        return t
