import os
import tempfile
from datetime import datetime
import numpy as np
import scipy.io.wavfile as wav


class Transcriber:
    """Lightweight transcription helper wrapping model I/O and file output.

    Usage example:
        t = Transcriber(output_file="transcription.txt")
        model = t.load_model("small", device="cpu")
        text = t.transcribe_buffer(buffer, model)
        t.write_line(text)
    """

    def __init__(self, output_file="transcription.txt", sample_rate=16000):
        self.output_file = output_file
        self.sample_rate = sample_rate
        self.transcript_context = ""

    def load_model(self, name, device="cpu", compute_type=None):
        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            raise RuntimeError("faster_whisper is required to load models") from e

        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"
        return WhisperModel(name, device=device, compute_type=compute_type)

    def passes_energy_gate(self, audio: np.ndarray, threshold: float = 0.0) -> bool:
        if threshold <= 0:
            return True
        rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
        return rms >= threshold

    def is_hallucination(self, text: str) -> bool:
        words = text.split()
        if len(words) < 6:
            return False
        ngrams = [tuple(words[i:i+4]) for i in range(len(words) - 3)]
        from collections import Counter

        return any(c > 2 for c in Counter(ngrams).values())

    def transcribe_buffer(self, buffer: list, model, prompt: str = "", fast: bool = True) -> str:
        """Concatenate a list of numpy arrays and run model.transcribe on a temporary wav file.

        `buffer` is a list of 1-D numpy arrays (int16 or float) that will be concatenated.
        """
        if not buffer:
            return ""
        audio = np.concatenate(buffer)
        if not self.passes_energy_gate(audio):
            return ""

        peak = np.abs(audio).max() if audio.size else 0
        if peak > 0:
            audio = (audio / peak * 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        try:
            wav.write(tmp, self.sample_rate, audio)
            if fast:
                segs, _ = model.transcribe(
                    tmp,
                    beam_size=3,
                    language="en",
                    vad_filter=True,
                    vad_parameters=dict(threshold=0.6),
                    temperature=0.0,
                    condition_on_previous_text=True,
                    initial_prompt=prompt or None,
                    no_speech_threshold=0.6,
                    compression_ratio_threshold=2.4,
                )
            else:
                segs, _ = model.transcribe(
                    tmp,
                    beam_size=5,
                    language="en",
                    vad_filter=True,
                    vad_parameters=dict(threshold=0.7),
                    temperature=[0.0, 0.2, 0.4],
                    condition_on_previous_text=True,
                    initial_prompt=prompt or None,
                    no_speech_threshold=0.6,
                    compression_ratio_threshold=2.4,
                )
            return " ".join(s.text for s in segs).strip()
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def write_line(self, text: str):
        if not text:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {text}\n")

    def replace_live_with_final(self, final_text: str, live_count: int = 0):
        try:
            with open(self.output_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            lines = []

        if live_count > 0 and len(lines) >= live_count:
            lines = lines[:-live_count]

        if final_text:
            lines.append(f"[{datetime.now().strftime('%H:%M:%S')}] {final_text}\n")

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def push_context(self, text: str, max_chars: int = 300):
        self.transcript_context = (self.transcript_context + " " + text).strip()[-max_chars:]
