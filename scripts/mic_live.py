"""Simple example: record from mic and transcribe."""
import sounddevice as sd
import soundfile as sf
import tempfile
from pathlib import Path
from transcriptions import Transcriber

DURATION = 5.0
SR = 16000

t = Transcriber()
model = t.load_model("small", device="cpu")

audio = sd.rec(int(DURATION * SR), samplerate=SR, channels=1, dtype="int16")
sd.wait()

text = t.transcribe_buffer([audio], model)
print(f">> {text}")

