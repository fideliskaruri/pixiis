# Transcriptions Library

A lightweight transcription helper library for [`faster_whisper`](https://github.com/SYSTRAN/faster-whisper) models.

## Installation

```bash
cd "d:\code\python projects"
pip install -e .
```

## Quick Start

### Live Microphone Transcription

```bash
python scripts/mic_live.py
```

Records 4-second audio chunks from your microphone and transcribes them in real-time.

### Batch File Processing

```bash
python scripts/batch_process.py
```

Watches the `inbox/` folder for audio files (`.wav`, `.mp3`, `.m4a`, `.flac`) and transcribes them to `batch_transcripts.txt`, moving processed files to `processed/`.

### Library Usage

```python
from transcriptions import Transcriber

t = Transcriber(output_file="transcription.txt")
model = t.load_model("base", device="cpu")
text = t.transcribe_buffer([audio_array], model)
t.write_line(text)
```

## Project Structure

```
transcriptions/
├── __init__.py            # Package exports
├── transcriber.py         # Core Transcriber class
scripts/
├── __init__.py
├── mic_live.py           # Real-time mic transcription
└── batch_process.py      # Batch file transcription
tests/
├── __init__.py
└── test_transcriber.py   # Unit tests
setup.py                  # Package setup
requirements.txt          # Dependencies
README.md                 # This file
.gitignore               # Git ignore rules
```

## API

### `Transcriber`

**Methods:**

- `load_model(name, device, compute_type)` — Load a Whisper model
- `transcribe_buffer(buffer, model, prompt="", fast=True)` — Transcribe audio samples
- `passes_energy_gate(audio, threshold)` — Check if audio passes energy threshold
- `is_hallucination(text)` — Detect Whisper hallucinations
- `write_line(text)` — Append transcript to output file
- `replace_live_with_final(final_text, live_count)` — Replace live lines with final
- `push_context(text, max_chars)` — Update transcript context

## Dependencies

- `faster-whisper`
- `numpy`
- `scipy`
- `sounddevice`
- `soundfile`
