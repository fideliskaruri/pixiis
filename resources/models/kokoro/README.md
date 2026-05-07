# Kokoro TTS model — bundle source

The TTS subsystem (Pane 2 / wave2-tts) expects two files in this
directory at NSIS build time:

- `kokoro-v1.0.onnx` (~325 MB) — the Kokoro v1.0 ONNX model.
- `voices-v1.0.bin` (~26 MB) — the packed voice-style table
  (np.savez of float32 npy arrays, 54 voices × 511 × 256).

Tauri's `bundle.resources` glob in `src-tauri/tauri.conf.json` ships
everything under `resources/models/kokoro/` into the installer; on first
run, `voice/tts.rs::ensure_model_files` copies the pair into
`%APPDATA%/pixiis/models/kokoro/` so subsequent loads come from a
writable location.

## Downloading

Both files are published as release assets on the upstream
`thewh1teagle/kokoro-onnx` GitHub repo:

```bash
curl -L -o kokoro-v1.0.onnx \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx

curl -L -o voices-v1.0.bin \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

If the `model-files-v1.0` tag has been superseded upstream, check the
releases page for the current asset URLs:

<https://github.com/thewh1teagle/kokoro-onnx/releases>

## Why these two files

The pipeline runs phonemes -> ONNX inference -> 24 kHz f32 audio. The
`.onnx` file is the inference graph; the `.bin` file is the per-voice
style embedding table picked at synthesis time. Both have to be present
for `voice_speak` to succeed — the engine surfaces a clean
`AppError::NotFound` if either is missing instead of panicking.

The choice of v1.0 (vs. the newer experimental tags) comes from the
Wave 1 Phase 0 spike (`spike/kokoro-bench/RESULTS.md`): perceptual
equivalence cosine 0.9991 vs. the Python `kokoro-onnx` reference at
this exact pair of files.

## Not bundled with the repo

These files are too large to commit to git. Fetch them locally before
running `./build.sh` if you want a self-contained installer; otherwise
the build still succeeds (the glob simply matches nothing) and TTS
returns `NotFound` until the user drops the files into
`%APPDATA%/pixiis/models/kokoro/` by hand.
