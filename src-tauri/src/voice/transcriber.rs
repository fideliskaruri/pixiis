//! Whisper-rs wrapper, adapted from `spike/whisper-bench/src/main.rs`.
//!
//! Wraps a single [`WhisperContext`] (model loaded once) and exposes
//! `transcribe(samples, fast)` — `fast=true` for the live model pass,
//! `fast=false` for the final post-release pass. Includes the spike's
//! hallucination filter and an RMS energy gate so we drop silent / noise
//! chunks before paying the whisper cost.

use std::collections::HashMap;
use std::path::Path;
use std::sync::Arc;

use parking_lot::Mutex;
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

use crate::error::{AppError, AppResult};

/// Energy threshold below which we skip the whisper call entirely.
/// Matches `pipeline.py::energy_threshold` default (300 on i16, ~0.009 on f32).
const ENERGY_THRESHOLD_F32: f32 = 0.009;

/// Repeated 4-gram hallucination guard, port of
/// `transcriber.py::is_hallucination`.
fn is_hallucination(text: &str) -> bool {
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.len() < 6 {
        return false;
    }
    let mut counts: HashMap<[&str; 4], u32> = HashMap::new();
    for window in words.windows(4) {
        let key: [&str; 4] = [window[0], window[1], window[2], window[3]];
        let entry = counts.entry(key).or_insert(0);
        *entry += 1;
        if *entry > 2 {
            return true;
        }
    }
    false
}

fn passes_energy_gate(samples: &[f32]) -> bool {
    if samples.is_empty() {
        return false;
    }
    let sum_sq: f32 = samples.iter().map(|s| s * s).sum();
    let rms = (sum_sq / samples.len() as f32).sqrt();
    rms >= ENERGY_THRESHOLD_F32
}

/// Loaded whisper context. `Arc<Transcriber>` is shared between the live and
/// final transcription paths — we only load the model once. Internally each
/// call creates its own [`whisper_rs::WhisperState`], because state is *not*
/// thread-safe in whisper-rs (matches the spike's per-iter pattern).
pub struct Transcriber {
    ctx: WhisperContext,
    threads: i32,
    /// Serialise `state.full()` calls; whisper.cpp itself is not reentrant
    /// across states sharing one context. Live + final compete for this lock.
    inflight: Mutex<()>,
}

impl Transcriber {
    /// Load `ggml-*.bin` from `model_path`. CPU-only build; the `--gpu`
    /// branch from the spike is dormant on hardware without CUDA/Metal.
    pub fn load(model_path: &Path) -> AppResult<Arc<Self>> {
        let path = model_path
            .to_str()
            .ok_or_else(|| AppError::InvalidArg("model path is not valid UTF-8".into()))?;

        let mut params = WhisperContextParameters::default();
        params.use_gpu = false;

        let ctx = WhisperContext::new_with_params(path, params)
            .map_err(|e| AppError::Other(format!("whisper load {}: {e}", model_path.display())))?;

        let threads = std::thread::available_parallelism()
            .map(|n| n.get() as i32)
            .unwrap_or(4);

        Ok(Arc::new(Self {
            ctx,
            threads,
            inflight: Mutex::new(()),
        }))
    }

    /// Transcribe a 16 kHz mono f32 PCM buffer. Returns an empty string when
    /// the buffer fails the energy gate, the model produced no text, or
    /// every emitted segment looks like a Whisper hallucination.
    ///
    /// `fast=true` uses beam=1 (greedy) and is suited to the rolling live
    /// pass; `fast=false` uses beam=5 for the final pass after the user
    /// releases the mic.
    pub fn transcribe(&self, samples: &[f32], fast: bool) -> AppResult<String> {
        if !passes_energy_gate(samples) {
            return Ok(String::new());
        }

        // Whisper rejects clips < 1 s — pad with silence so the segment
        // callback fires (mirrors spike RESULTS.md note about the wall).
        const MIN_SAMPLES_16K: usize = 16_000;
        let mut padded;
        let input: &[f32] = if samples.len() < MIN_SAMPLES_16K {
            padded = Vec::with_capacity(MIN_SAMPLES_16K);
            padded.extend_from_slice(samples);
            padded.resize(MIN_SAMPLES_16K, 0.0);
            &padded
        } else {
            samples
        };

        let _guard = self.inflight.lock();
        let mut state = self
            .ctx
            .create_state()
            .map_err(|e| AppError::Other(format!("whisper create_state: {e}")))?;

        let strategy = if fast {
            SamplingStrategy::Greedy { best_of: 1 }
        } else {
            SamplingStrategy::BeamSearch {
                beam_size: 5,
                patience: -1.0,
            }
        };
        let mut params = FullParams::new(strategy);
        params.set_n_threads(self.threads);
        params.set_language(Some("en"));
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_special(false);
        params.set_print_timestamps(false);
        params.set_translate(false);
        params.set_suppress_blank(true);

        state
            .full(params, input)
            .map_err(|e| AppError::Other(format!("whisper full(): {e}")))?;

        let n_segments = state
            .full_n_segments()
            .map_err(|e| AppError::Other(format!("whisper full_n_segments: {e}")))?;

        let mut transcript = String::new();
        for i in 0..n_segments {
            let seg = state
                .full_get_segment_text(i)
                .map_err(|e| AppError::Other(format!("whisper segment {i}: {e}")))?;
            transcript.push_str(seg.trim());
            transcript.push(' ');
        }
        let trimmed = transcript.trim().to_string();

        if is_hallucination(&trimmed) {
            return Ok(String::new());
        }
        Ok(trimmed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hallucination_short_passes() {
        assert!(!is_hallucination("hello world"));
    }

    #[test]
    fn hallucination_repeated_4gram_caught() {
        // 4-gram "thanks for watching the" repeats 3 times → hallucination.
        let text = "thanks for watching the video thanks for watching the video thanks for watching the video";
        assert!(is_hallucination(text));
    }

    #[test]
    fn energy_gate_drops_silence() {
        let silent = vec![0.0_f32; 1600];
        assert!(!passes_energy_gate(&silent));
    }

    #[test]
    fn energy_gate_passes_speech() {
        // 0.05 amplitude noise — well above 0.009 RMS threshold.
        let speech: Vec<f32> = (0..1600)
            .map(|i| 0.05 * ((i as f32) * 0.1).sin())
            .collect();
        assert!(passes_energy_gate(&speech));
    }
}
