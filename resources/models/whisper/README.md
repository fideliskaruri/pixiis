# Whisper models — bundle source

The voice subsystem expects `ggml-base.en-q5_0.bin` (~31 MB) to live in
this directory at NSIS build time. Tauri's `bundle.resources` glob in
`src-tauri/tauri.conf.json` ships everything under `resources/models/`
into the installer; on first run, `voice/model.rs::ensure_default_whisper_model`
copies the file into `%APPDATA%/pixiis/models/whisper/` so subsequent
loads come from a writable location.

## Downloading

The Q5_0 quantised `base.en` weights are mirrored on Hugging Face:

```bash
curl -L -o ggml-base.en-q5_0.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_0.bin
```

(SHA-256: `017c5d23...` — verify against the file listing on the HF page.)

The choice of Q5_0 over the larger f16 GGUF comes from the Wave 1 spike
results (`spike/whisper-bench/RESULTS.md` § Recommendations): Q5_0 is
~5× smaller with no measurable transcript-quality loss for this model
size, and avoids the WSL 9P load-time penalty that bit the f16 file in
the spike.

## Larger models

The Settings page (Pane 5) wires a "download larger model" button that
fetches `ggml-small.en-q5_0.bin` and `ggml-medium.en-q5_0.bin` directly
into `%APPDATA%/pixiis/models/whisper/` on demand. They are **not**
bundled — they total ~600 MB and would balloon the installer.
