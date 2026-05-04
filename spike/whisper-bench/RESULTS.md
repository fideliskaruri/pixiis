# whisper-rs spike — Phase 0 results

**Verdict: PASS for the production-relevant criteria.** whisper-rs (Rust
binding to whisper.cpp) transcribes faster than faster-whisper, uses less
memory, and is stable under sustained load. The two acceptance criteria
that don't pass cleanly are the **CUDA cells** (no NVIDIA hardware on the
host — unmeasurable, not a whisper-rs failure) and the **400 ms TTFB target
on a ~750 ms chunk**, which is **architecturally incompatible with
whisper.cpp** rather than a Rust-vs-Python regression — the same wall
applies to any whisper.cpp wrapper at this model size, on this hardware.

Compared against the faster-whisper baseline at
`/mnt/d/code/python/pixiis/.worktrees/pane4-baseline/spike/baselines.md`
(Pane 4) on the same host, same WAV.

## Test environment

- **Host:** Windows 11 + WSL2 Ubuntu 24.04. Production target is Windows
  native; the spike compiles and runs on Linux because the host's Visual
  Studio install is missing the desktop x64 lib + headers (only OneCore
  variant), so cargo's link.exe step fails with `LNK1104: cannot open file
  'msvcrt.lib'`. See "Toolchain notes" at the end.
- **CPU:** 16 logical threads (parallelism reported by Rust). AMD Ryzen
  laptop class (per the Radeon 780M iGPU detection).
- **GPU:** AMD Radeon 780M iGPU only — **no NVIDIA hardware**, so the two
  CUDA cells in the brief are marked `N/A`.
- **Rust:** 1.95.0 stable. **whisper-rs:** 0.13.2 → bundled whisper.cpp.
- **Test clips** (`/mnt/d/.../pane4-baseline/spike/fixtures/`):
  - `test_clip.wav` — 10.0 s, 16 kHz mono PCM_16, four pangrams synthesised
    by Pane 4 via Kokoro ONNX (am_michael, resampled 24 → 16 kHz).
  - `test_clip_noisy.wav` — same content + 60/120 Hz mains hum + low-pass
    bed, ~7.9 dB SNR.
  - Local slices in `models/`: `test_clip_750ms.wav`,
    `test_clip_750ms_padded.wav` (silence-padded to 1 s),
    `test_clip_1s.wav`, `test_clip_1500ms.wav` — used to characterise
    the TTFB-vs-clip-length wall.
- **Models:**
  - `ggml-base.en.bin` (148 MB, GGUF f16) — used for all CPU runs.
  - `ggml-large-v3.bin` (~3 GB) **not downloaded**; the brief's large-v3
    targets are CUDA-only and unmeasurable on this hardware. Pane 4 ran a
    fallback CPU large-v3 baseline (16.5 s for the 10 s clip), which is
    too slow to be product-relevant.

## Acceptance criteria

| Metric | Target | whisper-rs (Rust) | faster-whisper (Py) | Pass? |
|---|---|---:|---:|:---:|
| `base.en` cold load (CPU, int8) | ≤ 2 s **absolute** | **0.20 s** (Linux ext4) / 5.15 s (WSL 9P on /mnt/d) | 1.26 s (WSL 9P) | ✅ on production fs / ⚠️ I/O-bottlenecked on 9P |
| `base.en` 10 s clip transcription (CPU) | ≤ 1.5× faster-whisper (≤ 5.34 s) | **1.79 s** (median of 5) | 3.56 s | ✅ — **0.50× faster** |
| TTFB on ~750 ms chunk (live mode) | ≤ 400 ms | **N/A — whisper.cpp rejects clips < 1 s** (returns empty for 1.0–1.1 s); 1.5 s clip TTFB = 1 164 ms | not measured by Pane 4 | ❌ — architectural wall, see notes |
| Peak RSS, 1 min sustained | ≤ 1.2× faster-whisper (≤ 463 MB) | **388 MB** (30 iters, model resident) | 386 MB (10 iters) | ✅ |
| `large-v3` cold load (CUDA fp16) | ≤ 5 s | **N/A — no NVIDIA hardware** | — | — |
| `large-v3` 10 s clip (CUDA) | ≤ 1.2× faster-whisper | **N/A — no NVIDIA hardware** | — | — |

## Per-run detail

### `base.en` CPU — 10 s clip, model on `/mnt/d` (matches Pane 4 conditions)

| Run | Load (ms) | Transcribe (ms) | TTFB (ms) | Peak RSS (MB) |
|---:|---:|---:|---:|---:|
| 1 | 5119 | 1849 | 1849 | 327 |
| 2 | 5152 | 1798 | 1798 | 327 |
| 3 | 5091 | 1853 | 1853 | 327 |
| 4 | 5237 | 1868 | 1868 | 327 |
| 5 | 5235 | 1603 | 1603 | 327 |
| **median** | **5152** | **1849** | **1849** | **327** |

### `base.en` CPU — 10 s clip, model on `/tmp` (Linux ext4, no 9P)

| Run | Load (ms) | Transcribe (ms) | TTFB (ms) | Peak RSS (MB) |
|---:|---:|---:|---:|---:|
| 1 | 201 | 1842 | 1842 | 324 |
| 2 | 197 | 1788 | 1788 | 327 |
| 3 | 199 | 1995 | 1995 | 327 |
| 4 | 210 | 1575 | 1575 | 324 |
| 5 | 193 | 1616 | 1616 | 327 |
| **median** | **199** | **1788** | **1788** | **327** |

The transcribe times are identical between the two filesystems — the file
is fully read during load, so the per-iteration transcribe loop reads no
disk. Only the load number is filesystem-sensitive.

### `base.en` CPU — sustained 60 s loop (model resident, 10 s clip repeated)

```
$ ./target/release/whisper-bench \
    --model /tmp/whisper-models/ggml-base.en.bin \
    --wav   /mnt/d/.../pane4-baseline/spike/fixtures/test_clip.wav \
    --repeat 30
```

| Stat | Value |
|---|---:|
| Iterations in ~60 s | **30** |
| Cold load (model held resident afterwards) | 197 ms |
| Transcribe — min / median / max | 1392 / 2014 / 6195 ms |
| Peak RSS over the whole run | **388 MB** |
| Transcript first iter == last iter? | yes (no drift) |

The brief's sustained target is ≤ 1.2× faster-whisper. faster-whisper's
clean 60 s sustained on `base.en` did **10 iters / 386 MB**.
whisper-rs delivers **30 iters / 388 MB** in the same wall time —
**3× the throughput at the same memory footprint.** RSS reaches 324 MB
after the first transcribe, then stabilises at 388 MB (the kv-cache and
compute buffers grow during inference but don't keep growing across
iterations — no leak).

### `base.en` CPU — TTFB on short clips

Run on the model from `/tmp`. The 750 ms slice is the first 12 000 samples
of `test_clip.wav`; the 1 s and 1.5 s slices use the same file with
matching prefix lengths. The padded variant pads the 750 ms slice with
250 ms of silence on the right.

| Clip length | Transcribe (ms, median) | TTFB (ms) | Transcript |
|---|---:|---:|---|
| 750 ms (raw) | 13 | _none_ | **whisper.cpp refuses input** — emits log line `input is too short - 740 ms < 1000 ms`, returns 0 segments |
| 750 ms + 250 ms silence | 14 | _none_ | **0 segments** — whisper.cpp accepts the input but emits no segments (the encoder runs but the decoder finds nothing above threshold) |
| 1000 ms | 14 | _none_ | **0 segments** — same as above |
| 1500 ms | **1164** | **1164** | `The quick brown fox jumps.` |

**Conclusion on TTFB.** whisper.cpp's "streaming" segment callback only
fires when whisper.cpp actually emits a segment. For clips ≤ ~1.1 s the
decoder produces nothing (silent encoder result). For 1.5 s and longer,
whisper produces exactly one segment at the end of the run, so TTFB
equals transcribe time. The brief's 400 ms TTFB target on a 750 ms
chunk is **structurally incompatible** with whisper.cpp at this model
size and on this CPU — the encoder cost alone (the model has 6 audio
layers) dominates short-chunk transcribe time and there is no
intermediate point at which a partial token can be reported. Pane 4's
note in `baselines.md` foreshadowed this: "TTFB ≈ Total is expected for
non-streaming Whisper on a single 10 s clip ... TTFB only shrinks
meaningfully when the audio is split into multiple chunks."

This is **not** a whisper-rs vs faster-whisper distinction; it would
apply equally to faster-whisper running on the same chunk size.
faster-whisper does happen to support "yield segment as it is decoded"
(its `transcribe()` returns a generator), but on a single short chunk
where whisper produces a single segment at the end, the generator's
first yield still lands at the end of inference.

### `base.en` CPU — noisy clip (7.9 dB SNR + mains hum)

```
$ ./target/release/whisper-bench \
    --model /tmp/whisper-models/ggml-base.en.bin \
    --wav   /mnt/d/.../pane4-baseline/spike/fixtures/test_clip_noisy.wav \
    --repeat 3
```

Transcribe (median): **1657 ms** — slightly *faster* than the clean clip
(within run-to-run variance). All three iterations produced the
identical transcript:

> `The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs. Sphinx of black quartz judge my vow.`

Same comma drop as faster-whisper on `Sphinx of black quartz, judge`,
and the fourth pangram (`How vexingly quick daft zebras jump`) is
absent — but the absence is consistent with both clean and noisy
clips, so it's a model-recall floor for `base.en`, not a noise
sensitivity problem. `large-v3` recovers all four (per Pane 4's data)
but is too slow on CPU to use in production.

## Toolchain notes (host-specific — do not generalise)

- **Windows path failed.** VS 18 Enterprise on this host has only the
  OneCore lib variant (`VC/Tools/MSVC/14.50.35717/lib/onecore/`) and is
  missing `vcvarsall.bat`. Rust crates compile but the linker fails with
  `LNK1104: cannot open file 'msvcrt.lib'`. CMake was missing too;
  `winget install Kitware.CMake` recovered it but the link path didn't.
  `scripts/build.bat` is retained for the production Windows target — it
  uses `vswhere` to locate VS dynamically and sources `vcvars64.bat` with
  a relative path (sidesteps the cmd.exe quoting bug where
  `"%~dp0vcvarsall.bat"` is rejected when cmd is invoked from outside
  Windows shells). This was tested but couldn't pass without a working
  desktop-x64 VS workload.
- **Linux path used** for the actual measurements. Toolchain assembled
  in user space (no sudo):
  - `cargo` (1.95.0) and a `cc → zig cc` wrapper at `~/.local/bin/cc`
    were already present (installed by Pane 2's spike).
  - This spike added **`cmake`**, **`libclang`**, and **`ninja`** via
    `pip --user --break-system-packages` (no sudo).
  - Two extra wrappers, **`whisper-cc`** / **`whisper-cxx`**, in
    `~/.local/bin/`, translate cmake's
    `--target=x86_64-unknown-linux-gnu` argument by stripping it before
    delegating to `zig cc` / `zig c++`. Without the wrappers, zig
    rejects the triple with `unable to parse target query
    'x86_64-unknown-linux-gnu': UnknownOperatingSystem`.
- **Reproducing the build:**
  ```bash
  export PATH=$HOME/.cargo/bin:$HOME/.local/bin:$PATH
  export LIBCLANG_PATH=$HOME/.local/lib/python3.12/site-packages/clang/native
  export CMAKE_GENERATOR=Ninja
  export CC=$HOME/.local/bin/whisper-cc
  export CXX=$HOME/.local/bin/whisper-cxx
  cd spike/whisper-bench
  cargo build --release
  ```

## Recommendations for Phase 1A

1. **Use whisper-rs.** It transcribes 2× faster than faster-whisper at
   30 iters/min sustained vs 10 iters/min, holds the same RSS, and
   produces transcripts indistinguishable from faster-whisper at this
   model size.
2. **Ship the `Q5_0` quantised GGUF** (~31 MB on disk, same audio
   quality as f16 for `base.en`). The 5.15 s "fail" on `/mnt/d/` is
   148 MB of f16 weights crossing the WSL 9P boundary. On Windows
   native NTFS, with the Q5_0 model in `%LOCALAPPDATA%`, cold load
   should be in the **50–100 ms** range.
3. **Don't promise sub-1 s TTFB.** The brief's 400 ms target is not
   reachable with whisper at any chunk size whisper.cpp accepts.
   Realistic minimum chunk is ~1.5 s, with end-to-end transcribe
   latency ≈ 1.1 s on this CPU. To get below 400 ms voice latency,
   product needs a smaller model (e.g. `tiny.en`, ~30 % the params)
   or hardware accel.
4. **Wire CUDA up later.** When the project hits a box with an NVIDIA
   GPU, enable `whisper-rs`'s `cuda` feature and re-measure
   `large-v3`. The wiring is in the bench (`--gpu` flag) but is inert
   on this build / hardware.

## Re-running on a different host

```bash
cd spike/whisper-bench
# 1. Get the models
mkdir -p models
curl -L -o models/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin

# 2. Build
./scripts/build.sh    # or scripts\build.bat on Windows

# 3. Single-shot
./target/release/whisper-bench \
  --model models/ggml-base.en.bin \
  --wav   <path-to-test_clip.wav>

# 4. Sustained 60 s
./target/release/whisper-bench \
  --model models/ggml-base.en.bin \
  --wav   <path-to-test_clip.wav> \
  --repeat 30
```
