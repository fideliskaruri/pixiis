"""Audio capture via sounddevice with thread-safe buffering."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import numpy as np

from pixiis.core.config import get_config

if TYPE_CHECKING:
    import sounddevice as sd


class AudioCapture:
    """Wraps sounddevice.InputStream with a thread-safe chunk buffer.

    Usage:
        cap = AudioCapture()
        cap.start()
        # ... later ...
        chunks = cap.get_buffer()
        cap.stop()
    """

    def __init__(
        self,
        sample_rate: int | None = None,
        chunk_size: int | None = None,
    ) -> None:
        cfg = get_config()
        self.sample_rate = sample_rate or cfg.get("voice.sample_rate", 16000)
        self.chunk_size = chunk_size or cfg.get("voice.chunk_size", 64)

        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._recording_event = threading.Event()
        self._stream: sd.InputStream | None = None

    # ── public API ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Open the audio stream and begin recording."""
        import sounddevice as sd

        self._recording_event.set()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.chunk_size,
            callback=self._audio_callback,
            latency="low",
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop recording and close the stream."""
        self._recording_event.clear()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def get_buffer(self) -> list[np.ndarray]:
        """Return a copy of the current buffer."""
        with self._lock:
            return list(self._buffer)

    def clear_buffer(self) -> None:
        """Discard all buffered audio."""
        with self._lock:
            self._buffer.clear()

    @property
    def is_recording(self) -> bool:
        """True while the capture is actively recording."""
        return self._recording_event.is_set()

    @property
    def recording_event(self) -> threading.Event:
        """Expose the recording event for external coordination."""
        return self._recording_event

    # ── internals ────────────────────────────────────────────────────────

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        """sounddevice stream callback — appends chunks while recording."""
        if self._recording_event.is_set():
            with self._lock:
                self._buffer.append(indata.copy().flatten())
