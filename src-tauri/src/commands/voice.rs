//! Voice push-to-talk commands. Backed by [`crate::voice::VoiceService`],
//! set up in `lib.rs::run::setup` and stored in app state.
//!
//! `voice_start` opens the mic and emits `voice:state` + streaming
//! `voice:partial` events; `voice_stop` runs the final pass, emits
//! `voice:final`, and returns the transcript.

use std::io::{Read, Write};
use std::sync::Arc;

use tauri::{AppHandle, Emitter, State};

use crate::error::{AppError, AppResult};
use crate::types::{TranscriptionEvent, VoiceDevice};
use crate::voice::{audio_capture, model, text_injection, VoiceService};

/// `Option<Arc<VoiceService>>` so the command surface degrades gracefully
/// when the whisper model wasn't found at startup — `voice_start` returns
/// `Other("voice unavailable: ...")` and the rest no-op or report `[]`.
pub type VoiceState<'a> = State<'a, Arc<VoiceServiceSlot>>;

/// Wrapper Tauri can `manage()`. Holds either a live service or the reason
/// startup failed (so the UI can surface it).
pub struct VoiceServiceSlot {
    pub service: Option<Arc<VoiceService>>,
    pub init_error: Option<String>,
}

impl VoiceServiceSlot {
    fn get(&self) -> AppResult<Arc<VoiceService>> {
        self.service.clone().ok_or_else(|| {
            AppError::Other(format!(
                "voice unavailable: {}",
                self.init_error
                    .clone()
                    .unwrap_or_else(|| "service not initialised".into())
            ))
        })
    }
}

#[tauri::command]
pub async fn voice_start(state: VoiceState<'_>) -> AppResult<()> {
    let svc = state.get()?;
    svc.start()
}

#[tauri::command]
pub async fn voice_stop(state: VoiceState<'_>) -> AppResult<TranscriptionEvent> {
    let svc = state.get()?;
    // Final pass blocks the calling thread on whisper — push it onto the
    // blocking pool so the async runtime stays responsive.
    tokio::task::spawn_blocking(move || svc.stop())
        .await
        .map_err(|e| AppError::Other(format!("voice_stop join: {e}")))?
}

#[tauri::command]
pub async fn voice_get_devices() -> AppResult<Vec<VoiceDevice>> {
    tokio::task::spawn_blocking(audio_capture::list_devices)
        .await
        .map_err(|e| AppError::Other(format!("voice_get_devices join: {e}")))?
}

#[tauri::command]
pub async fn voice_set_device(state: VoiceState<'_>, device_id: String) -> AppResult<()> {
    let svc = state.get()?;
    svc.set_device(if device_id.is_empty() {
        None
    } else {
        Some(device_id)
    });
    Ok(())
}

#[tauri::command]
pub async fn voice_inject_text(text: String) -> AppResult<()> {
    tokio::task::spawn_blocking(move || text_injection::inject(&text))
        .await
        .map_err(|e| AppError::Other(format!("voice_inject_text join: {e}")))?
}

#[tauri::command]
pub async fn voice_get_transcript_log(
    state: VoiceState<'_>,
    limit: Option<u32>,
) -> AppResult<Vec<TranscriptionEvent>> {
    Ok(state
        .service
        .as_ref()
        .map(|s| s.transcript_log(limit))
        .unwrap_or_default())
}

/// Status payload for `voice_status` — lets the frontend distinguish
/// "model genuinely missing → offer download" from "model present but
/// init crashed for another reason → surface raw error".
#[derive(serde::Serialize, Clone, Debug)]
pub struct VoiceStatus {
    /// Whether the service is initialised and `voice_start` will succeed.
    pub available: bool,
    /// True when the service is unavailable specifically because no
    /// whisper model was found at startup. The UI uses this to swap
    /// "MODEL NOT INSTALLED" for the raw error string.
    pub model_missing: bool,
    /// Human-readable init error (if any), for power-user diagnostics.
    pub init_error: Option<String>,
    /// Where the bundled model is expected to live on disk. Useful for
    /// the Settings page's "model: bundled" status line.
    pub model_filename: String,
}

#[tauri::command]
pub async fn voice_status(state: VoiceState<'_>) -> AppResult<VoiceStatus> {
    let init_error = state.init_error.clone();
    let model_missing = init_error
        .as_ref()
        .map(|s| s.to_ascii_lowercase().contains("not found"))
        .unwrap_or(false);
    Ok(VoiceStatus {
        available: state.service.is_some(),
        model_missing,
        init_error,
        model_filename: model::DEFAULT_WHISPER_FILENAME.to_string(),
    })
}

/// Progress event emitted by `voice_download_model`. UI renders a
/// simple "Downloading 57 MB voice model…" with a percent bar driven by
/// `bytes_done / bytes_total`.
#[derive(serde::Serialize, Clone, Debug)]
pub struct VoiceDownloadEvent {
    pub bytes_done: u64,
    pub bytes_total: u64,
    /// Set on the final (`done = true`) emission. Empty on success.
    pub error: Option<String>,
    pub done: bool,
}

const EVT_DOWNLOAD: &str = "voice:model:downloading";

/// Download the bundled whisper model from HuggingFace. Streams to
/// `%APPDATA%/pixiis/models/whisper/<filename>` and emits progress on
/// `voice:model:downloading`. The frontend should re-call
/// `voice_status` when `done = true && error.is_none()` to confirm the
/// service has come up — most reliably done by reloading the Settings
/// page or the entire app, since `VoiceService::new` runs once at boot.
#[tauri::command]
pub async fn voice_download_model(app: AppHandle) -> AppResult<String> {
    let target = model::user_whisper_path();
    if let Err(e) = model::ensure_parent(&target) {
        let msg = format!("could not create models dir: {e}");
        let _ = app.emit(
            EVT_DOWNLOAD,
            VoiceDownloadEvent {
                bytes_done: 0,
                bytes_total: 0,
                error: Some(msg.clone()),
                done: true,
            },
        );
        return Err(AppError::Other(msg));
    }

    let url = model::DEFAULT_WHISPER_HF_URL.to_string();
    let app_for_thread = app.clone();
    let target_for_thread = target.clone();

    // The download runs on the blocking pool because reqwest's blocking
    // client + chunked file write is the simplest correctness story
    // (vs. tokio + async streams, which would force us to bring an
    // additional executor flavour into the voice module). Whisper init
    // already lives on a blocking thread elsewhere — same pattern.
    let result = tokio::task::spawn_blocking(move || -> Result<String, String> {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(300))
            .build()
            .map_err(|e| format!("http client: {e}"))?;
        let mut resp = client
            .get(&url)
            .send()
            .map_err(|e| format!("GET {url}: {e}"))?;
        if !resp.status().is_success() {
            return Err(format!("GET {url}: HTTP {}", resp.status()));
        }
        let total = resp.content_length().unwrap_or(0);
        let _ = app_for_thread.emit(
            EVT_DOWNLOAD,
            VoiceDownloadEvent {
                bytes_done: 0,
                bytes_total: total,
                error: None,
                done: false,
            },
        );

        // Write to a sibling temp file first, rename on success — keeps
        // a half-written .bin from poisoning the user-dir lookup if the
        // network drops mid-download.
        let tmp = target_for_thread.with_extension("bin.tmp");
        let mut out = std::fs::File::create(&tmp)
            .map_err(|e| format!("create {}: {e}", tmp.display()))?;
        let mut buf = [0u8; 64 * 1024];
        let mut done: u64 = 0;
        let mut last_emit = std::time::Instant::now();
        loop {
            let n = match resp.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => n,
                Err(e) => return Err(format!("read: {e}")),
            };
            out.write_all(&buf[..n])
                .map_err(|e| format!("write {}: {e}", tmp.display()))?;
            done += n as u64;
            if last_emit.elapsed() >= std::time::Duration::from_millis(150) {
                let _ = app_for_thread.emit(
                    EVT_DOWNLOAD,
                    VoiceDownloadEvent {
                        bytes_done: done,
                        bytes_total: total,
                        error: None,
                        done: false,
                    },
                );
                last_emit = std::time::Instant::now();
            }
        }
        out.sync_all().map_err(|e| format!("sync: {e}"))?;
        drop(out);
        std::fs::rename(&tmp, &target_for_thread).map_err(|e| {
            format!(
                "rename {} -> {}: {e}",
                tmp.display(),
                target_for_thread.display()
            )
        })?;
        let _ = app_for_thread.emit(
            EVT_DOWNLOAD,
            VoiceDownloadEvent {
                bytes_done: done,
                bytes_total: total.max(done),
                error: None,
                done: true,
            },
        );
        Ok(target_for_thread.display().to_string())
    })
    .await
    .map_err(|e| AppError::Other(format!("voice_download_model join: {e}")))?;

    match result {
        Ok(path) => Ok(path),
        Err(msg) => {
            let _ = app.emit(
                EVT_DOWNLOAD,
                VoiceDownloadEvent {
                    bytes_done: 0,
                    bytes_total: 0,
                    error: Some(msg.clone()),
                    done: true,
                },
            );
            Err(AppError::Other(msg))
        }
    }
}

