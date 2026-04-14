"""Voice Activity Detection backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


VAD_FRAME_SIZE = 512


@runtime_checkable
class VADBackend(Protocol):
    """Minimal interface every VAD backend must satisfy."""

    def is_speech(self, samples: np.ndarray, sample_rate: int) -> bool: ...


# ── Silero VAD ───────────────────────────────────────────────────────────


class SileroVAD:
    """Silero VAD via torch.hub (snakers4/silero-vad).

    Matches shout.py behaviour: runs inference on a 512-sample frame,
    returns True when confidence > 0.5.
    """

    def __init__(self) -> None:
        import torch

        self._model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad", model="silero_vad"
        )
        self._torch = torch

    def is_speech(self, samples: np.ndarray, sample_rate: int) -> bool:
        frame = samples[:VAD_FRAME_SIZE]
        if len(frame) < VAD_FRAME_SIZE:
            frame = np.pad(frame, (0, VAD_FRAME_SIZE - len(frame)))
        audio_f32 = self._torch.from_numpy(frame.astype(np.float32)) / 32768.0
        confidence = self._model(audio_f32, sample_rate).item()
        return confidence > 0.5


# ── WebRTC VAD ───────────────────────────────────────────────────────────


class WebRTCVAD:
    """WebRTC VAD wrapper (webrtcvad package).

    Expects 160 samples (10 ms at 16 kHz) of int16 audio, matching
    experimental_vad.py.
    """

    WEBRTC_FRAME = 160  # 10 ms at 16 kHz

    def __init__(self, aggressiveness: int = 1) -> None:
        import webrtcvad

        self._vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, samples: np.ndarray, sample_rate: int) -> bool:
        frame = samples[: self.WEBRTC_FRAME].astype(np.int16)
        if len(frame) < self.WEBRTC_FRAME:
            frame = np.pad(frame, (0, self.WEBRTC_FRAME - len(frame)))
        try:
            return self._vad.is_speech(frame.tobytes(), sample_rate)
        except Exception:
            return False


# ── Energy VAD ───────────────────────────────────────────────────────────


class EnergyVAD:
    """Simple RMS energy threshold fallback — no external deps."""

    def __init__(self, threshold: float = 300.0) -> None:
        self.threshold = threshold

    def is_speech(self, samples: np.ndarray, sample_rate: int) -> bool:
        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        return rms >= self.threshold


# ── factory ──────────────────────────────────────────────────────────────


def get_vad(backend_name: str = "silero") -> VADBackend:
    """Instantiate a VAD backend by name.

    Falls back to EnergyVAD if the requested backend's dependency is
    missing.
    """
    name = backend_name.lower()

    if name == "silero":
        try:
            return SileroVAD()
        except ImportError:
            print("[vad] torch not available, falling back to EnergyVAD")
            return EnergyVAD()

    if name == "webrtc":
        try:
            return WebRTCVAD()
        except ImportError:
            print("[vad] webrtcvad not available, falling back to EnergyVAD")
            return EnergyVAD()

    if name == "energy":
        return EnergyVAD()

    raise ValueError(f"Unknown VAD backend: {backend_name!r}")
