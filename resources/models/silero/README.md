# Silero VAD model — bundle source

`silero_vad.onnx` (~2 MB) ships from this directory when the
`silero-vad` Cargo feature is enabled in `src-tauri/Cargo.toml`. Without
the feature flag, voice falls back to a simple RMS energy gate
(`voice/vad.rs::EnergyVad`) and this file is never read.

## Downloading

```bash
curl -L -o silero_vad.onnx \
  https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx
```

Tag/commit: see the upstream `snakers4/silero-vad` releases page.

## Why feature-gated

The Wave 2 voice brief asks for "Silero ONNX (via `ort`) primary,
energy threshold fallback." The `ort` 2.0 release-candidate API still
moves between rc versions and onnxruntime.dll has to be resolvable at
runtime, which costs deployment complexity. Keeping it behind a feature
flag means the default `cargo build --release` doesn't depend on either —
turn it on once `ort` stabilises and `onnxruntime.dll` is bundled.
