"""Batch transcribe audio files from inbox/ folder."""
from pathlib import Path
import time
import shutil
from transcriptions import Transcriber

INBOX = Path("inbox")
PROCESSED = Path("processed")
INBOX.mkdir(exist_ok=True)
PROCESSED.mkdir(exist_ok=True)

t = Transcriber(output_file="batch_transcripts.txt")
model = t.load_model("small", device="cpu")

seen = set()
print("Watching inbox/ for audio files...")

while True:
    for p in sorted(INBOX.iterdir()):
        if p.is_file() and p.suffix.lower() in [".wav", ".mp3"] and p not in seen:
            seen.add(p)
            text = t.transcribe_buffer([p], model)
            print(f"{p.name}: {text}")
            t.write_line(text)
            shutil.move(str(p), str(PROCESSED / p.name))
    time.sleep(1)

