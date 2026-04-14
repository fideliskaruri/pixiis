"""
Live transcriber with experimental features for testing:
- Deduplication (fix repetition)
- Alternative VAD backends (Silero vs WebRTC)
- Different model combinations
- Streaming real-time architecture

Usage:
  python test_impl.py --live-model tiny --final-model large-v3 --device cuda
  python test_impl.py --vad webrtc  (test WebRTC VAD instead of Silero)
  python test_impl.py --no-dedup    (disable deduplication for comparison)
"""

import sounddevice as sd
import numpy as np
import torch
import queue
import threading
import pygame
import os
import time
import argparse
import signal
import sys
from transcriptions import Transcriber

# ── args ──────────────────────────────────────────────────────────────────────
AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
parser = argparse.ArgumentParser(description="Live transcriber with experimental features")
parser.add_argument("--live-model", choices=AVAILABLE_MODELS, default="tiny")
parser.add_argument("--final-model", choices=AVAILABLE_MODELS, default="large-v3")
parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
parser.add_argument("--vad", choices=["silero", "webrtc"], default="silero")
parser.add_argument("--energy-threshold", type=float, default=300.0)
parser.add_argument("--no-dedup", action="store_true", help="Disable deduplication")
args = parser.parse_args()

compute_type = "float16" if args.device == "cuda" else "int8"

# ── models ────────────────────────────────────────────────────────────────────
t = Transcriber(output_file="transcription.txt", sample_rate=16000)

print(f"Loading live model ({args.live_model})...")
whisper_live = t.load_model(args.live_model, device=args.device, compute_type=compute_type)

if args.final_model == args.live_model:
    whisper_final = whisper_live
else:
    print(f"Loading final model ({args.final_model})...")
    whisper_final = t.load_model(args.final_model, device=args.device, compute_type=compute_type)

# ── VAD setup ─────────────────────────────────────────────────────────────────
print(f"Loading VAD ({args.vad})...")
if args.vad == "silero":
    vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
    (get_speech_timestamps, _, read_audio, *_) = utils
    VAD_TYPE = "silero"
elif args.vad == "webrtc":
    try:
        import webrtcvad
        vad_model = webrtcvad.Vad()
        VAD_TYPE = "webrtc"
    except ImportError:
        print("webrtcvad not installed. Falling back to Silero.")
        vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
        (get_speech_timestamps, _, read_audio, *_) = utils
        VAD_TYPE = "silero"

# ── constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHUNK_SIZE = 512
VAD_SILENCE_WAIT = 0.4
VAD_FRAME_SIZE = 512
MIN_SPEECH_SECONDS = 0.75
MAX_LIVE_SECONDS = 5.0
OUTPUT_FILE = "transcription.txt"
TRIGGER_BUTTON = 0

direct_buffer = []
direct_buffer_lock = threading.Lock()
recording_event = threading.Event()
last_transcribed_index = 0
transcription_queue = queue.Queue()
live_line_ids = []
live_line_ids_lock = threading.Lock()

shutdown_event = threading.Event()

# ── deduplication ─────────────────────────────────────────────────────────────
last_outputs = []
last_outputs_lock = threading.Lock()
MAX_DEDUP_HISTORY = 10

def is_duplicate(text: str) -> bool:
    """Check if text was recently output."""
    if not text or args.no_dedup:
        return False
    with last_outputs_lock:
        for prev in last_outputs:
            if text.strip() == prev.strip():
                return True
    return False

def add_to_history(text: str):
    """Track output for deduplication."""
    if text and not args.no_dedup:
        with last_outputs_lock:
            last_outputs.append(text)
            last_outputs[:] = last_outputs[-MAX_DEDUP_HISTORY:]

# ── helpers ───────────────────────────────────────────────────────────────────
def passes_energy_gate(audio_chunk: np.ndarray) -> bool:
    if args.energy_threshold <= 0:
        return True
    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
    return rms >= args.energy_threshold

def check_vad_speech(samples: np.ndarray) -> bool:
    """Check if audio contains speech."""
    if len(samples) < VAD_FRAME_SIZE:
        samples = np.pad(samples, (0, VAD_FRAME_SIZE - len(samples)))
    
    if VAD_TYPE == "silero":
        audio_f32 = torch.from_numpy(samples[:VAD_FRAME_SIZE].astype(np.float32)) / 32768.0
        confidence = vad_model(audio_f32, SAMPLE_RATE).item()
        return confidence > 0.5
    
    elif VAD_TYPE == "webrtc":
        audio_int16 = samples[:512].astype(np.int16)
        try:
            return vad_model.is_speech(audio_int16[:160].tobytes(), SAMPLE_RATE)
        except Exception:
            return False
    
    return True

# ── audio callback ────────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    if recording_event.is_set():
        with direct_buffer_lock:
            direct_buffer.append(indata.copy().flatten())

# ── workers ───────────────────────────────────────────────────────────────────
def transcription_worker():
    while not shutdown_event.is_set():
        try:
            buffer_copy, label, model, is_final = transcription_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            start_time = time.time()
            text = t.transcribe_buffer(buffer_copy, model, prompt="", fast=not is_final)
            elapsed = time.time() - start_time

            if text:
                if is_final:
                    print(f"{label}>> {text}  [{elapsed:.2f}s]")
                else:
                    if is_duplicate(text):
                        print(f"{label}[DEDUP] {text}")
                    else:
                        print(f"{label}>> {text}  [{elapsed:.2f}s]")
                
                if is_final:
                    with live_line_ids_lock:
                        live_count = len(live_line_ids)
                        live_line_ids.clear()
                    t.replace_live_with_final(text, live_count=live_count)
                    add_to_history(text)
                else:
                    # Only write if not duplicate
                    if not is_duplicate(text):
                        t.write_line(text)
                        add_to_history(text)
                        with live_line_ids_lock:
                            live_line_ids.append(1)

            if is_final:
                print()

        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            transcription_queue.task_done()

def rolling_transcribe_loop():
    """VAD-based streaming: instant transcription when speech ends."""
    global last_transcribed_index
    while not shutdown_event.is_set():
        recording_event.wait(timeout=0.5)
        if shutdown_event.is_set():
            break
        if not recording_event.is_set():
            continue

        last_transcribed_index = 0
        last_had_speech = False

        while recording_event.is_set() and not shutdown_event.is_set():
            time.sleep(0.1)

            if not recording_event.is_set():
                break

            with direct_buffer_lock:
                current_index = len(direct_buffer)
                new_chunk_count = current_index - last_transcribed_index

            if new_chunk_count <= 0:
                continue

            elapsed_seconds = new_chunk_count * CHUNK_SIZE / SAMPLE_RATE

            if elapsed_seconds < MIN_SPEECH_SECONDS:
                continue

            force_cut = elapsed_seconds >= MAX_LIVE_SECONDS

            if not force_cut:
                silence_check_chunks = int(SAMPLE_RATE * VAD_SILENCE_WAIT / CHUNK_SIZE)
                with direct_buffer_lock:
                    recent = direct_buffer[max(0, current_index - silence_check_chunks):current_index]

                if not recent:
                    continue

                all_silent = all(
                    not passes_energy_gate(c) or not check_vad_speech(c)
                    for c in recent
                )

                if not all_silent:
                    last_had_speech = True
                    continue

                if not last_had_speech:
                    continue

            with direct_buffer_lock:
                new_chunks = direct_buffer[last_transcribed_index:current_index]

            min_chunks = int(SAMPLE_RATE * MIN_SPEECH_SECONDS / CHUNK_SIZE)
            if len(new_chunks) < min_chunks:
                continue

            last_transcribed_index = current_index
            last_had_speech = False
            transcription_queue.put((new_chunks, "[live] ", whisper_live, False))

def controller_loop():
    global last_transcribed_index
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("No controller found.")
        return

    controller = pygame.joystick.Joystick(0)
    controller.init()
    print(f"Controller: {controller.get_name()}")
    print(f"Live: {args.live_model} | Final: {args.final_model} | Device: {args.device} | VAD: {args.vad} | Dedup: {not args.no_dedup}")
    print(f"Hold A to record, release for final.\n")

    while not shutdown_event.is_set():
        pygame.event.pump()
        button_held = controller.get_button(TRIGGER_BUTTON)

        if button_held and not recording_event.is_set():
            with direct_buffer_lock:
                direct_buffer.clear()
            last_transcribed_index = 0
            with live_line_ids_lock:
                live_line_ids.clear()
            last_outputs.clear()
            recording_event.set()
            print("  [recording...]")

        elif not button_held and recording_event.is_set():
            recording_event.clear()
            time.sleep(0.05)

            with direct_buffer_lock:
                full_buffer = direct_buffer.copy()
                direct_buffer.clear()

            if full_buffer:
                transcription_queue.put((full_buffer, "[final] ", whisper_final, True))

        pygame.time.wait(10)

# ── graceful shutdown ─────────────────────────────────────────────────────────
def shutdown(signum=None, frame=None):
    print("\n  [shutting down...]")
    shutdown_event.set()
    recording_event.set()
    try:
        pygame.quit()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ── start threads ─────────────────────────────────────────────────────────────
threading.Thread(target=transcription_worker, daemon=True).start()
threading.Thread(target=rolling_transcribe_loop, daemon=True).start()
threading.Thread(target=controller_loop, daemon=True).start()

print(f"Listening... output -> {OUTPUT_FILE} (Ctrl+C to stop)\n")

with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                    blocksize=CHUNK_SIZE, callback=audio_callback, latency='low'):
    while not shutdown_event.is_set():
        sd.sleep(100)
