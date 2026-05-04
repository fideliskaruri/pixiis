"""faster-whisper baseline runner for Phase 0.

Measures load time, total wall time, time-to-first-segment (TTFB), and peak RSS
for `base.en` (CPU int8) and `large-v3` (CUDA fp16 if available, else CPU int8)
on the shared 10 s test clip. Reports median over 3 runs per cell.

Run from the spike/ directory with the spike .venv:

    .venv/bin/python3 baseline_runner.py
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil

SPIKE_DIR = Path(__file__).resolve().parent
FIXTURES = SPIKE_DIR / "fixtures"
DEFAULT_CLIP = FIXTURES / "test_clip.wav"


def _has_cuda() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


@dataclass
class RunMetrics:
    load_s: float
    total_s: float
    ttfb_ms: float
    peak_rss_mb: float
    transcript: str


@dataclass
class Cell:
    model: str
    device: str
    compute: str
    runs: list[RunMetrics] = field(default_factory=list)

    def median(self, attr: str) -> float:
        return statistics.median(getattr(r, attr) for r in self.runs)

    def transcript(self) -> str:
        return self.runs[-1].transcript if self.runs else ""


class _RSSWatcher:
    """Polls RSS at ~10 ms cadence on a background thread."""

    def __init__(self, proc: psutil.Process, interval: float = 0.01) -> None:
        self.proc = proc
        self.interval = interval
        self.peak = proc.memory_info().rss
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                rss = self.proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            if rss > self.peak:
                self.peak = rss
            self._stop.wait(self.interval)

    def __enter__(self) -> "_RSSWatcher":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)


def _run_once(model_name: str, device: str, compute_type: str, clip: Path) -> RunMetrics:
    """One full cycle: fresh model load, transcribe, capture metrics."""
    from faster_whisper import WhisperModel

    proc = psutil.Process()
    gc.collect()

    # ── load
    with _RSSWatcher(proc) as w_load:
        t0 = time.perf_counter()
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        load_s = time.perf_counter() - t0
    load_peak = w_load.peak

    # ── transcribe (streaming generator → measure TTFB on first segment)
    with _RSSWatcher(proc) as w_run:
        t1 = time.perf_counter()
        segs_gen, _info = model.transcribe(
            str(clip),
            beam_size=5,
            language="en",
            vad_filter=False,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        first_seg = None
        collected: list[str] = []
        for i, seg in enumerate(segs_gen):
            if i == 0:
                first_seg = time.perf_counter()
            collected.append(seg.text)
        t2 = time.perf_counter()
    run_peak = w_run.peak

    if first_seg is None:
        ttfb_ms = float("nan")
    else:
        ttfb_ms = (first_seg - t1) * 1000.0

    transcript = " ".join(s.strip() for s in collected).strip()
    peak_mb = max(load_peak, run_peak) / (1024 * 1024)

    # release the model so the next iteration starts cold
    del model
    gc.collect()

    return RunMetrics(
        load_s=load_s,
        total_s=t2 - t1,
        ttfb_ms=ttfb_ms,
        peak_rss_mb=peak_mb,
        transcript=transcript,
    )


def _sustained(model_name: str, device: str, compute_type: str, clip: Path, seconds: float = 60.0) -> dict:
    """Loop transcribe the clip for ~`seconds`, report peak RSS + iteration count."""
    from faster_whisper import WhisperModel

    proc = psutil.Process()
    gc.collect()
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    iters = 0
    end = time.perf_counter() + seconds
    with _RSSWatcher(proc) as w:
        while time.perf_counter() < end:
            segs_gen, _ = model.transcribe(
                str(clip),
                beam_size=5,
                language="en",
                vad_filter=False,
                condition_on_previous_text=False,
                temperature=0.0,
            )
            for _ in segs_gen:
                pass
            iters += 1
    del model
    gc.collect()
    return {
        "model": model_name,
        "device": device,
        "compute": compute_type,
        "iterations": iters,
        "wall_s": seconds,
        "peak_rss_mb": w.peak / (1024 * 1024),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", type=Path, default=DEFAULT_CLIP)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--sustained-seconds", type=float, default=60.0)
    ap.add_argument("--skip-large", action="store_true", help="skip large-v3 (long downloads / slow CPU)")
    ap.add_argument("--skip-sustained", action="store_true")
    ap.add_argument("--json-out", type=Path, default=SPIKE_DIR / "baseline_results.json")
    args = ap.parse_args()

    if not args.clip.exists():
        print(f"clip not found: {args.clip}", file=sys.stderr)
        return 1

    cuda = _has_cuda()
    print(f"CUDA available: {cuda}")
    print(f"Clip: {args.clip}  ({args.clip.stat().st_size} bytes)")

    cells: list[Cell] = [Cell(model="base.en", device="cpu", compute="int8")]
    if not args.skip_large:
        if cuda:
            cells.append(Cell(model="large-v3", device="cuda", compute="float16"))
        else:
            cells.append(Cell(model="large-v3", device="cpu", compute="int8"))

    for cell in cells:
        print(f"\n=== {cell.model} | {cell.device} | {cell.compute} ===")
        for i in range(args.repeats):
            print(f"  run {i + 1}/{args.repeats} ...", flush=True)
            m = _run_once(cell.model, cell.device, cell.compute, args.clip)
            print(
                f"    load={m.load_s:.2f}s  total={m.total_s:.2f}s  ttfb={m.ttfb_ms:.0f}ms  rss={m.peak_rss_mb:.0f}MB"
            )
            cell.runs.append(m)

    sustained = None
    if not args.skip_sustained:
        sm = cells[0]  # base.en — the realistic always-resident model
        print(f"\n=== sustained {args.sustained_seconds:.0f}s | {sm.model} | {sm.device} | {sm.compute} ===")
        sustained = _sustained(sm.model, sm.device, sm.compute, args.clip, args.sustained_seconds)
        print(
            f"  iters={sustained['iterations']}  peak_rss={sustained['peak_rss_mb']:.0f}MB"
        )

    # ── JSON dump for downstream consumers
    payload = {
        "cuda_available": cuda,
        "clip": str(args.clip),
        "repeats": args.repeats,
        "cells": [
            {
                "model": c.model,
                "device": c.device,
                "compute": c.compute,
                "median": {
                    "load_s": c.median("load_s"),
                    "total_s": c.median("total_s"),
                    "ttfb_ms": c.median("ttfb_ms"),
                    "peak_rss_mb": c.median("peak_rss_mb"),
                },
                "transcript": c.transcript(),
                "runs": [vars(r) for r in c.runs],
            }
            for c in cells
        ],
        "sustained": sustained,
    }
    args.json_out.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {args.json_out}")

    # ── markdown table on stdout
    print("\n| Model | Device | Compute | Load (s) | Total (s) | TTFB (ms) | Peak RSS (MB) | Transcript |")
    print("|---|---|---|---:|---:|---:|---:|---|")
    for c in cells:
        tr = c.transcript().replace("|", "\\|")
        if len(tr) > 80:
            tr = tr[:77] + "..."
        print(
            f"| {c.model} | {c.device} | {c.compute} | "
            f"{c.median('load_s'):.2f} | {c.median('total_s'):.2f} | "
            f"{c.median('ttfb_ms'):.0f} | {c.median('peak_rss_mb'):.0f} | {tr} |"
        )
    if sustained:
        print(
            f"\nSustained {sustained['wall_s']:.0f}s on {sustained['model']} "
            f"({sustained['device']}, {sustained['compute']}): "
            f"{sustained['iterations']} iters, peak RSS {sustained['peak_rss_mb']:.0f} MB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
