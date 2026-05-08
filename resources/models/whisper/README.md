# Whisper models — bundle source

The voice subsystem expects `ggml-base.en-q5_1.bin` (~57 MB) to live in
this directory at NSIS build time. As of v0.2.1 the file is **committed
to the repo** so the installer ships with voice working out of the box —
no manual download step. Tauri's `bundle.resources` glob in
`src-tauri/tauri.conf.json` ships everything under `resources/models/whisper/`
into the installer; on first run, `voice/model.rs::ensure_default_whisper_model`
copies the file into `%APPDATA%/pixiis/models/whisper/` so subsequent
loads come from a writable location.

## Re-downloading

If the file is ever missing or corrupt, fetch it from Hugging Face:

```bash
curl -L -o ggml-base.en-q5_1.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin
```

The Q5_1 quantised `base.en` weights are mirrored on Hugging Face. We
originally targeted Q5_0, but `ggml-base.en-q5_0.bin` is no longer
mirrored — Q5_1 is the closest available variant of the same base.en
checkpoint.

The choice of Q5_1 over the larger f16 GGUF comes from the Wave 1 spike
results (`spike/whisper-bench/RESULTS.md` § Recommendations): the small
quantised variants are several times smaller with no measurable
transcript-quality loss for this model size, and avoid the WSL 9P
load-time penalty that bit the f16 file in the spike.

## Larger models

The Settings page (Pane 5) wires a "download larger model" button that
fetches `ggml-small.en-q5_1.bin` and `ggml-medium.en-q5_0.bin` directly
into `%APPDATA%/pixiis/models/whisper/` on demand. They are **not**
bundled — they total ~600 MB and would balloon the installer.
