//! Push-to-talk recording pipeline. Mirrors the Python
//! `voice/pipeline.py::VoicePipeline` topology in Rust.
//!
//! While a session is active there are three concurrent actors:
//!
//! 1. **cpal callback thread** — owns the input stream, normalises samples
//!    to 16 kHz mono f32, pushes them to a shared rolling buffer.
//! 2. **rolling-transcribe worker** — every ~100 ms looks at the unread tail
//!    of the buffer and decides whether to enqueue a *live* (partial)
//!    transcription based on min-speech / max-live timing and a VAD silence
//!    check. Mirrors `pipeline.py::_rolling_transcribe_loop`.
//! 3. **transcription worker** — single thread that owns the whisper-rs
//!    context and serialises live + final transcription requests, emitting
//!    `voice:partial` / `voice:final` events as it goes.
//!
//! All three exit cleanly when [`Session::stop`] is called: the cpal stream
//! is dropped, both workers see `recording=false` plus a `Stop` message on
//! the transcription channel, and `stop` blocks for the final pass and
//! returns its text.

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use crossbeam_channel::{bounded, unbounded, Receiver, Sender};
use parking_lot::Mutex;
use tauri::{AppHandle, Emitter};

use crate::error::{AppError, AppResult};
use crate::types::TranscriptionEvent;
use crate::voice::audio_capture::{AudioCapture, TARGET_SAMPLE_RATE};
use crate::voice::transcriber::Transcriber;
use crate::voice::vad::{Vad, SILERO_FRAME};

const EVENT_PARTIAL: &str = "voice:partial";
const EVENT_FINAL: &str = "voice:final";
const EVENT_STATE: &str = "voice:state";

/// Tuning constants — copied from `pipeline.py` so behaviour matches
/// across the language boundary.
const MIN_SPEECH_SECONDS: f32 = 0.75;
const MAX_LIVE_SECONDS: f32 = 5.0;
const VAD_SILENCE_WAIT_S: f32 = 0.5;
const ROLLING_OVERLAP_S: f32 = 0.5;
const POLL_INTERVAL: Duration = Duration::from_millis(100);

#[derive(Debug, Clone, serde::Serialize)]
struct StateEvent<'a> {
    state: &'a str,
}

#[derive(Debug)]
enum TxRequest {
    /// Live partial — best-effort, may be deduped against history.
    Live(Vec<f32>),
    /// Final pass — `done_tx` receives the transcript so `voice_stop` can
    /// return it. `Stop` also tells the worker thread to exit.
    Final {
        samples: Vec<f32>,
        done_tx: Sender<String>,
    },
    Stop,
}

/// One push-to-talk session. Owns the cpal capture + the two background
/// threads. Dropped at the end of `voice_stop`.
struct Session {
    capture: Option<AudioCapture>,
    rolling_handle: Option<thread::JoinHandle<()>>,
    transcribe_handle: Option<thread::JoinHandle<()>>,
    tx_sender: Sender<TxRequest>,
    /// The shared rolling buffer of f32 samples at 16 kHz mono.
    buffer: Arc<Mutex<Vec<f32>>>,
    recording: Arc<AtomicBool>,
}

/// Outer service: lives for the app's lifetime, holds the loaded whisper
/// context + VAD, and owns at most one [`Session`] at a time.
pub struct VoiceService {
    app: AppHandle,
    transcriber: Arc<Transcriber>,
    vad: Arc<dyn Vad>,
    session: Mutex<Option<Session>>,
    /// User's chosen device (`None` ⇒ system default). Updated by
    /// `voice_set_device`; consumed at the next `voice_start`.
    selected_device: Mutex<Option<String>>,
    /// Append-only transcript log. Cleared only by app restart.
    transcript_log: Mutex<Vec<TranscriptionEvent>>,
    /// History of recent live transcripts, used for dedup. Bounded.
    dedup: Mutex<Vec<String>>,
}

impl VoiceService {
    /// Build the service. `model_path` must point at a usable
    /// `ggml-*.bin` Whisper model; `vad_model_path` is best-effort
    /// (Silero ONNX) and falls back to the energy gate.
    pub fn new(
        app: AppHandle,
        model_path: PathBuf,
        vad_model_path: Option<PathBuf>,
    ) -> AppResult<Arc<Self>> {
        let transcriber = Transcriber::load(&model_path)?;
        let vad: Arc<dyn Vad> = Arc::from(crate::voice::vad::build(vad_model_path.as_deref()));

        Ok(Arc::new(Self {
            app,
            transcriber,
            vad,
            session: Mutex::new(None),
            selected_device: Mutex::new(None),
            transcript_log: Mutex::new(Vec::new()),
            dedup: Mutex::new(Vec::new()),
        }))
    }

    pub fn set_device(&self, device_id: Option<String>) {
        *self.selected_device.lock() = device_id;
    }

    pub fn transcript_log(&self, limit: Option<u32>) -> Vec<TranscriptionEvent> {
        let log = self.transcript_log.lock();
        match limit {
            Some(n) if (n as usize) < log.len() => {
                let start = log.len() - n as usize;
                log[start..].to_vec()
            }
            _ => log.clone(),
        }
    }

    /// Begin recording and emit `voice:state { listening }`. Returns
    /// `InvalidArg` if a session is already running.
    pub fn start(self: &Arc<Self>) -> AppResult<()> {
        let mut session_slot = self.session.lock();
        if session_slot.is_some() {
            return Err(AppError::InvalidArg("voice session already active".into()));
        }

        let buffer: Arc<Mutex<Vec<f32>>> = Arc::new(Mutex::new(Vec::with_capacity(
            (TARGET_SAMPLE_RATE * 30) as usize,
        )));
        let recording = Arc::new(AtomicBool::new(true));

        // Transcription worker: holds the whisper context, serialises
        // live + final passes, emits events, applies dedup.
        let (tx_sender, tx_receiver) = unbounded::<TxRequest>();
        let transcribe_handle = self.spawn_transcribe_worker(tx_receiver);

        // Rolling worker: polls the buffer and queues live requests.
        let rolling_handle = self.spawn_rolling_worker(
            buffer.clone(),
            recording.clone(),
            tx_sender.clone(),
        );

        // cpal capture: pushes new samples into the buffer.
        let capture_buffer = buffer.clone();
        let capture_recording = recording.clone();
        let device = self.selected_device.lock().clone();
        let capture = AudioCapture::start(device.as_deref(), move |chunk| {
            if !capture_recording.load(Ordering::Relaxed) {
                return;
            }
            capture_buffer.lock().extend_from_slice(&chunk);
        })?;

        *session_slot = Some(Session {
            capture: Some(capture),
            rolling_handle: Some(rolling_handle),
            transcribe_handle: Some(transcribe_handle),
            tx_sender,
            buffer,
            recording,
        });

        let _ = self
            .app
            .emit(EVENT_STATE, StateEvent { state: "listening" });
        Ok(())
    }

    /// Stop the running session, run a synchronous final transcription,
    /// emit `voice:final` + `voice:state { idle }`, and return the
    /// transcript. Returns `InvalidArg` if no session is running.
    pub fn stop(&self) -> AppResult<TranscriptionEvent> {
        let mut session = self
            .session
            .lock()
            .take()
            .ok_or_else(|| AppError::InvalidArg("no active voice session".into()))?;

        // Stop the cpal stream first so no new samples land mid-final-pass.
        session.recording.store(false, Ordering::Release);
        if let Some(capture) = session.capture.take() {
            capture.stop();
        }

        // Snapshot the full buffer for the final pass.
        let final_samples: Vec<f32> = session.buffer.lock().clone();

        let (done_tx, done_rx) = bounded::<String>(1);
        let _ = session.tx_sender.send(TxRequest::Final {
            samples: final_samples,
            done_tx,
        });
        let _ = session.tx_sender.send(TxRequest::Stop);

        if let Some(h) = session.rolling_handle.take() {
            let _ = h.join();
        }

        let final_text = done_rx
            .recv_timeout(Duration::from_secs(30))
            .unwrap_or_default();

        if let Some(h) = session.transcribe_handle.take() {
            let _ = h.join();
        }

        let evt = TranscriptionEvent {
            text: final_text.clone(),
            is_final: true,
            timestamp: now_secs(),
        };
        let _ = self.app.emit(EVENT_FINAL, &evt);
        let _ = self
            .app
            .emit(EVENT_STATE, StateEvent { state: "idle" });

        // The worker already pushed it into the log when it published
        // `voice:final`, so we don't double-record here.

        Ok(evt)
    }

    fn spawn_rolling_worker(
        self: &Arc<Self>,
        buffer: Arc<Mutex<Vec<f32>>>,
        recording: Arc<AtomicBool>,
        tx: Sender<TxRequest>,
    ) -> thread::JoinHandle<()> {
        let svc = Arc::clone(self);
        thread::Builder::new()
            .name("voice-rolling".into())
            .spawn(move || {
                let sample_rate = TARGET_SAMPLE_RATE as usize;
                let min_chunk = (sample_rate as f32 * MIN_SPEECH_SECONDS) as usize;
                let max_chunk = (sample_rate as f32 * MAX_LIVE_SECONDS) as usize;
                let silence_chunk = (sample_rate as f32 * VAD_SILENCE_WAIT_S) as usize;
                let overlap = (sample_rate as f32 * ROLLING_OVERLAP_S) as usize;

                let mut last_index: usize = 0;
                let mut last_had_speech = false;

                while recording.load(Ordering::Acquire) {
                    thread::sleep(POLL_INTERVAL);

                    let current_index = buffer.lock().len();
                    let new_samples = current_index.saturating_sub(last_index);
                    if new_samples < min_chunk {
                        continue;
                    }

                    let force_cut = new_samples >= max_chunk;
                    if !force_cut {
                        // Tail-of-buffer silence check via VAD on SILERO_FRAME-sized windows.
                        let tail_start = current_index.saturating_sub(silence_chunk);
                        let tail = {
                            let buf = buffer.lock();
                            buf[tail_start..current_index].to_vec()
                        };
                        if tail.is_empty() {
                            continue;
                        }
                        let any_speech = tail
                            .chunks(SILERO_FRAME)
                            .any(|w| svc.vad.is_speech(w, TARGET_SAMPLE_RATE));
                        if any_speech {
                            last_had_speech = true;
                            continue;
                        }
                        if !last_had_speech {
                            // Still all silence and we've never heard speech in
                            // this window — keep waiting.
                            continue;
                        }
                    }

                    let overlap_start = last_index.saturating_sub(overlap);
                    let chunk: Vec<f32> = {
                        let buf = buffer.lock();
                        buf[overlap_start..current_index].to_vec()
                    };
                    last_index = current_index;
                    last_had_speech = false;

                    let _ = tx.send(TxRequest::Live(chunk));
                }
            })
            .expect("spawn rolling worker")
    }

    fn spawn_transcribe_worker(
        self: &Arc<Self>,
        rx: Receiver<TxRequest>,
    ) -> thread::JoinHandle<()> {
        let svc = Arc::clone(self);
        thread::Builder::new()
            .name("voice-transcribe".into())
            .spawn(move || {
                while let Ok(req) = rx.recv() {
                    match req {
                        TxRequest::Stop => break,
                        TxRequest::Live(samples) => {
                            let text = svc
                                .transcriber
                                .transcribe(&samples, true)
                                .unwrap_or_default();
                            if text.is_empty() || svc.is_duplicate(&text) {
                                continue;
                            }
                            svc.remember(text.clone());
                            let evt = TranscriptionEvent {
                                text: text.clone(),
                                is_final: false,
                                timestamp: now_secs(),
                            };
                            {
                                let mut log = svc.transcript_log.lock();
                                log.push(evt.clone());
                                if log.len() > 1024 {
                                    let drop = log.len() - 1024;
                                    log.drain(0..drop);
                                }
                            }
                            let _ = svc.app.emit(EVENT_PARTIAL, &evt);
                        }
                        TxRequest::Final { samples, done_tx } => {
                            let text = svc
                                .transcriber
                                .transcribe(&samples, false)
                                .unwrap_or_default();
                            svc.remember(text.clone());
                            let evt = TranscriptionEvent {
                                text: text.clone(),
                                is_final: true,
                                timestamp: now_secs(),
                            };
                            svc.transcript_log.lock().push(evt);
                            let _ = done_tx.send(text);
                        }
                    }
                }
            })
            .expect("spawn transcribe worker")
    }

    fn is_duplicate(&self, text: &str) -> bool {
        let history = self.dedup.lock();
        let trimmed = text.trim();
        if trimmed.is_empty() {
            return false;
        }
        history.iter().any(|prev| prev.trim() == trimmed)
    }

    fn remember(&self, text: String) {
        if text.is_empty() {
            return;
        }
        let mut history = self.dedup.lock();
        history.push(text);
        // Match `pipeline.py::MAX_DEDUP_HISTORY = 10`.
        if history.len() > 10 {
            let drop = history.len() - 10;
            history.drain(0..drop);
        }
    }
}

fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}
