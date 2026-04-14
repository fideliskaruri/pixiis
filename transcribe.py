import sounddevice as sd
import numpy as np
import threading
import pygame
import time
import argparse
from transcriptions import Transcriber

# ── args ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Real-time transcription")
parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
args = parser.parse_args()

# ── model ─────────────────────────────────────────────────────────────────────
t = Transcriber(output_file="transcription.txt", sample_rate=16000)
print("Loading model...")
model = t.load_model("large", device=args.device)

# ── constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHUNK_SIZE = 512
OUTPUT_FILE = "transcription.txt"

audio_buffer = []
audio_buffer_lock = threading.Lock()
recording_event = threading.Event()

# ── audio callback ────────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    if recording_event.is_set():
        with audio_buffer_lock:
            audio_buffer.append(indata.copy().flatten())

# ── controller loop ───────────────────────────────────────────────────────────
def controller_loop():
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No controller found.")
        return
    ctrl = pygame.joystick.Joystick(0)
    ctrl.init()
    print(f"Controller: {ctrl.get_name()}")
    print(f"Model: large | Device: {args.device}")
    print(f"Hold A to record, release to transcribe.\n")

    while True:
        pygame.event.pump()
        held = ctrl.get_button(0)

        if held and not recording_event.is_set():
            with audio_buffer_lock:
                audio_buffer.clear()
            recording_event.set()
            print("  [recording...]")

        elif not held and recording_event.is_set():
            recording_event.clear()
            time.sleep(0.05)
            with audio_buffer_lock:
                buf = audio_buffer.copy()
                audio_buffer.clear()
            
            if buf:
                start = time.time()
                text = t.transcribe_buffer(buf, model, prompt="", fast=False)
                elapsed = time.time() - start
                
                if text and not t.is_hallucination(text):
                    print(f">> {text}  [{elapsed:.2f}s]")
                    t.write_line(text)
                elif text:
                    print(f"  [hallucination filtered]")

        pygame.time.wait(10)

# ── start ─────────────────────────────────────────────────────────────────────
threading.Thread(target=controller_loop, daemon=True).start()

print(f"Listening... output -> {OUTPUT_FILE} (Ctrl+C to stop)\n")

try:
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                        blocksize=CHUNK_SIZE, callback=audio_callback, latency='low'):
        while True:
            time.sleep(0.1)
except KeyboardInterrupt:
    print("\n  [stopped]")
