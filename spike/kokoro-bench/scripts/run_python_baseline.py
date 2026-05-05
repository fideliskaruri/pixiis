"""Run kokoro-onnx (Python) on the same inputs as the Rust spike.

Writes a 24 kHz mono float32 WAV plus a JSON metrics blob to stdout.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--voices", required=True)
    p.add_argument("--voice", default="am_michael")
    p.add_argument("--text", default=None)
    p.add_argument("--phonemes", default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--phonemes-out", default=None,
                   help="If set, save the espeak/phonemizer output here for the Rust side.")
    args = p.parse_args()

    if not (args.text or args.phonemes):
        raise SystemExit("supply --text or --phonemes")
    if args.text and args.phonemes:
        raise SystemExit("supply only one of --text/--phonemes")

    t0 = time.perf_counter()
    kokoro = Kokoro(args.model, args.voices)
    load_ms = (time.perf_counter() - t0) * 1000.0

    if args.phonemes is not None:
        phonemes = args.phonemes
        is_phonemes = True
    else:
        # Run phonemizer separately so we can dump the result for comparison.
        phonemes = kokoro.tokenizer.phonemize(args.text, lang="en-us")
        is_phonemes = True

    if args.phonemes_out:
        Path(args.phonemes_out).write_text(phonemes, encoding="utf-8")

    t0 = time.perf_counter()
    samples, sr = kokoro.create(
        phonemes,
        voice=args.voice,
        speed=args.speed,
        lang="en-us",
        is_phonemes=is_phonemes,
        trim=False,  # match Rust spike: no auto-trim
    )
    infer_ms = (time.perf_counter() - t0) * 1000.0

    sf.write(args.out, samples, sr, subtype="FLOAT")

    audio_duration = len(samples) / sr
    print(json.dumps({
        "phonemes": phonemes,
        "phoneme_count": len(phonemes),
        "audio_samples": int(len(samples)),
        "audio_duration_s": audio_duration,
        "model_load_ms": load_ms,
        "inference_ms": infer_ms,
        "sample_rate": int(sr),
        "rtf": (infer_ms / 1000.0) / max(audio_duration, 1e-9),
        "out_path": args.out,
    }, indent=2))


if __name__ == "__main__":
    main()
