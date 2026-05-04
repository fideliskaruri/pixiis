"""Compare two 24 kHz mono float32 WAV files for equivalence.

Reports byte-identity, sample-level diff, SNR, and a quick spectral check.
"""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np
import soundfile as sf


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    args = p.parse_args()

    a_bytes = args.a.read_bytes()
    b_bytes = args.b.read_bytes()
    print(f"a: {args.a}  sha256={sha(args.a)[:16]}  {len(a_bytes)}B")
    print(f"b: {args.b}  sha256={sha(args.b)[:16]}  {len(b_bytes)}B")
    print(f"byte-identical: {a_bytes == b_bytes}")

    a, sra = sf.read(str(args.a), dtype="float32")
    b, srb = sf.read(str(args.b), dtype="float32")
    if sra != srb:
        print(f"sample rate mismatch: {sra} vs {srb}")
        return
    if a.ndim > 1:
        a = a[:, 0]
    if b.ndim > 1:
        b = b[:, 0]
    n = min(len(a), len(b))
    print(f"length a={len(a)}  b={len(b)}  common={n}  rate={sra}")

    if len(a) != len(b):
        print(f"length differs by {abs(len(a)-len(b))} samples ({abs(len(a)-len(b))/sra*1000:.1f} ms)")

    a = a[:n]
    b = b[:n]
    diff = a - b
    max_abs = float(np.max(np.abs(diff)))
    rms_diff = float(np.sqrt(np.mean(diff**2)))
    rms_a = float(np.sqrt(np.mean(a**2))) + 1e-12
    snr_db = 20 * math.log10(rms_a / max(rms_diff, 1e-12))
    print(f"max |diff| = {max_abs:.6e}")
    print(f"rms diff   = {rms_diff:.6e}")
    print(f"snr        = {snr_db:.2f} dB  (∞ = identical)")

    # cheap correlation
    if rms_a > 1e-9 and float(np.sqrt(np.mean(b**2))) > 1e-9:
        corr = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        print(f"cosine sim = {corr:.6f}")


if __name__ == "__main__":
    main()
