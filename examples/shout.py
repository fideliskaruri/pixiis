import sounddevice as sd
import numpy as np
import io
import scipy.io.wavfile as wav
import torch
import queue
import threading
import pygame
import tempfile
import os
import soundfile
import urllib.request
from kokoro_onnx import Kokoro
from datetime import datetime
import time
import argparse
import subprocess
import sys
import signal
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from transcriptions import Transcriber

# ── auto-reload ───────────────────────────────────────────────────────────────
class ReloadHandler(FileSystemEventHandler):
    def __init__(self, script_path):
        self.script_path = script_path
        self.last_reload = time.time()

    def on_modified(self, event):
        if event.src_path.endswith(self.script_path):
            if time.time() - self.last_reload < 1.0:
                return
            self.last_reload = time.time()
            print("\n  [code changed, reloading...]\n")
            subprocess.Popen([sys.executable] + sys.argv)
            os._exit(0)

script_name = os.path.basename(__file__)
observer = Observer()
observer.schedule(ReloadHandler(script_name), path=".", recursive=False)
observer.start()

# ── args ──────────────────────────────────────────────────────────────────────
AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]

parser = argparse.ArgumentParser(description="Real-time transcription with TTS readback")
parser.add_argument("--live-model", choices=AVAILABLE_MODELS, default="large-v3")
parser.add_argument("--final-model", choices=AVAILABLE_MODELS, default="large-v3")
parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
parser.add_argument("--energy-threshold", type=float, default=300.0,
                    help="RMS energy gate — audio below this is ignored (0 to disable)")
parser.add_argument("--tts-voice", default="am_michael", help="Kokoro TTS voice name")
parser.add_argument("--tts-speed", type=float, default=1.0, help="TTS playback speed")
args = parser.parse_args()

compute_type = "float16" if args.device == "cuda" else "int8"

# ── models ────────────────────────────────────────────────────────────────────
t = Transcriber(output_file="transcription.txt", sample_rate=16000)

print(f"Loading Whisper live model ({args.live_model})...")
whisper_live = t.load_model(args.live_model, device=args.device, compute_type=compute_type)

if args.final_model == args.live_model:
    whisper_final = whisper_live
else:
    print(f"Loading Whisper final model ({args.final_model})...")
    whisper_final = t.load_model(args.final_model, device=args.device, compute_type=compute_type)

print("Loading Silero VAD...")
vad_model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad')
(get_speech_timestamps, _, read_audio, *_) = utils

# ── TTS setup ─────────────────────────────────────────────────────────────────
MODELS_DIR = os.path.join(os.path.expanduser("~"), ".cache", "kokoro")
ONNX_PATH = os.path.join(MODELS_DIR, "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(MODELS_DIR, "voices-v1.0.bin")
KOKORO_ONNX_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
KOKORO_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

def download_file(url: str, dest: str):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f"Downloading {os.path.basename(dest)}...")
    def progress(count, block_size, total_size):
        percent = min(int(count * block_size * 100 / total_size), 100)
        print(f"\r  {percent}%", end="", flush=True)
    urllib.request.urlretrieve(url, dest, reporthook=progress)
    print()

print("Loading Kokoro TTS...")
if not os.path.exists(ONNX_PATH):
    download_file(KOKORO_ONNX_URL, ONNX_PATH)
if not os.path.exists(VOICES_PATH):
    download_file(KOKORO_VOICES_URL, VOICES_PATH)
kokoro = Kokoro(ONNX_PATH, VOICES_PATH)

# ── constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHUNK_SIZE = 64
VAD_SILENCE_WAIT = 0.5
VAD_FRAME_SIZE = 512
MIN_SPEECH_SECONDS = 0.75  # balance: fast response + decent accuracy
MAX_LIVE_SECONDS = 5.0
OUTPUT_FILE = "transcription.txt"
TRIGGER_BUTTON = 0

direct_buffer = []
direct_buffer_lock = threading.Lock()
recording_event = threading.Event()
last_transcribed_index = 0
transcription_queue = queue.Queue()
tts_queue = queue.Queue()
live_line_ids = []
live_line_ids_lock = threading.Lock()

transcript_context = ""
transcript_context_lock = threading.Lock()
MAX_CONTEXT_CHARS = 224

shutdown_event = threading.Event()

# ── deduplication ─────────────────────────────────────────────────────────────
last_outputs = []  # track recent transcriptions to filter duplicates
last_outputs_lock = threading.Lock()
MAX_DEDUP_HISTORY = 10

def is_duplicate(text: str) -> bool:
    """Check if text was recently output."""
    if not text:
        return False
    with last_outputs_lock:
        for prev in last_outputs:
            if text.strip() == prev.strip():
                return True
    return False

def add_to_history(text: str):
    """Track output for deduplication."""
    if text:
        with last_outputs_lock:
            last_outputs.append(text)
            last_outputs[:] = last_outputs[-MAX_DEDUP_HISTORY:]

# ── energy gate ───────────────────────────────────────────────────────────────
def passes_energy_gate(audio_chunk: np.ndarray) -> bool:
    if args.energy_threshold <= 0:
        return True
    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
    return rms >= args.energy_threshold

# ── VAD helper ────────────────────────────────────────────────────────────────
def check_vad_speech(samples: np.ndarray) -> bool:
    if len(samples) < VAD_FRAME_SIZE:
        samples = np.pad(samples, (0, VAD_FRAME_SIZE - len(samples)))
    audio_f32 = torch.from_numpy(samples[:VAD_FRAME_SIZE].astype(np.float32)) / 32768.0
    confidence = vad_model(audio_f32, SAMPLE_RATE).item()
    return confidence > 0.5

# ── audio callback ────────────────────────────────────────────────────────────
def audio_callback(indata, frames, time_info, status):
    if recording_event.is_set():
        with direct_buffer_lock:
            direct_buffer.append(indata.copy().flatten())

# ── workers ───────────────────────────────────────────────────────────────────
def transcription_worker():
    global transcript_context, live_line_ids
    while not shutdown_event.is_set():
        try:
            buffer_copy, label, model, is_final = transcription_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            # Disable context prompting to reduce hallucinations
            prompt = ""

            start_time = time.time()
            text = t.transcribe_buffer(buffer_copy, model, prompt=prompt, fast=not is_final)  # fast for live, slow for final
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
                    tts_queue.put(text)
                    add_to_history(text)
                else:
                    # Only write if not duplicate
                    if not is_duplicate(text):
                        t.write_line(text)
                        add_to_history(text)
                        with live_line_ids_lock:
                            live_line_ids.append(1)  # just track count

            if is_final:
                with transcript_context_lock:
                    transcript_context = ""
                print()

        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            transcription_queue.task_done()

def rolling_transcribe_loop():
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

            overlap_chunks = int(SAMPLE_RATE * 0.5 / CHUNK_SIZE)
            with direct_buffer_lock:
                overlap_start = max(0, last_transcribed_index - overlap_chunks)
                new_chunks = direct_buffer[overlap_start:current_index]

            min_chunks = int(SAMPLE_RATE * MIN_SPEECH_SECONDS / CHUNK_SIZE)
            if len(new_chunks) < min_chunks:
                continue

            last_transcribed_index = current_index
            last_had_speech = False
            transcription_queue.put((new_chunks, "[live] ", whisper_live, False))

def tts_worker():
    pygame.mixer.init()
    while not shutdown_event.is_set():
        try:
            text = tts_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            t = time.time()
            samples, sample_rate = kokoro.create(
                text, voice=args.tts_voice, speed=args.tts_speed, lang="en-us"
            )
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                tmp_path = f.name
            soundfile.write(tmp_path, samples, sample_rate)
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and not shutdown_event.is_set():
                pygame.time.wait(50)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            print(f"  [TTS took {time.time() - t:.2f}s]")
        except Exception as e:
            print(f"TTS error: {e}")

def controller_loop():
    global last_transcribed_index
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("No controller found. Plug in your Xbox controller and restart.")
        return

    controller = pygame.joystick.Joystick(0)
    controller.init()
    print(f"Controller connected: {controller.get_name()}")
    print(f"Live: {args.live_model} | Final: {args.final_model} | Device: {args.device}")
    print(f"Energy gate: {args.energy_threshold} | TTS voice: {args.tts_voice}")
    print(f"Hold button {TRIGGER_BUTTON} (A) to record. Release for final transcript + TTS.\n")

    while not shutdown_event.is_set():
        pygame.event.pump()
        button_held = controller.get_button(TRIGGER_BUTTON)

        if button_held and not recording_event.is_set():
            with direct_buffer_lock:
                direct_buffer.clear()
            last_transcribed_index = 0
            with transcript_context_lock:
                transcript_context = ""
            with live_line_ids_lock:
                live_line_ids.clear()
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
    observer.stop()
    try:
        pygame.quit()
    except Exception:
        pass
    if os.path.exists("temp_utterance.wav"):
        try:
            os.unlink("temp_utterance.wav")
        except OSError:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ── start threads ─────────────────────────────────────────────────────────────
threading.Thread(target=transcription_worker, daemon=True).start()
threading.Thread(target=rolling_transcribe_loop, daemon=True).start()
threading.Thread(target=controller_loop, daemon=True).start()
threading.Thread(target=tts_worker, daemon=True).start()

print(f"Listening... output -> {OUTPUT_FILE} (Ctrl+C to stop)\n")

with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16',
                    blocksize=CHUNK_SIZE, callback=audio_callback,
                    latency='low'):
    while not shutdown_event.is_set():
        sd.sleep(100)
