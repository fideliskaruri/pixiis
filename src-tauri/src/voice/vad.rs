//! Voice Activity Detection — trait + two impls.
//!
//! - [`SileroVad`] (only with the `silero-vad` Cargo feature): ONNX model via
//!   `ort` (load-dynamic). Matches the Python `vad.py::SileroVAD` behaviour:
//!   feeds 512-sample frames at 16 kHz, calls speech if confidence > 0.5.
//! - [`EnergyVad`]: dependency-free RMS fallback. Always compiled. Used when
//!   the ONNX file isn't on disk yet, when the feature is off, or when the
//!   ort runtime can't load `onnxruntime.dll`.
//!
//! Both impls take **f32 mono samples in [-1, 1]** — the audio capture
//! layer normalises everything to that representation upstream.

use std::path::Path;

pub const SILERO_FRAME: usize = 512;

pub trait Vad: Send + Sync {
    fn is_speech(&self, samples: &[f32], sample_rate: u32) -> bool;
}

// ── Energy fallback ─────────────────────────────────────────────────────────

pub struct EnergyVad {
    threshold: f32,
}

impl EnergyVad {
    pub const DEFAULT_THRESHOLD: f32 = 0.009; // ~300 on i16 / 32768

    pub fn new(threshold: f32) -> Self {
        Self { threshold }
    }
}

impl Default for EnergyVad {
    fn default() -> Self {
        Self::new(Self::DEFAULT_THRESHOLD)
    }
}

impl Vad for EnergyVad {
    fn is_speech(&self, samples: &[f32], _sample_rate: u32) -> bool {
        if samples.is_empty() {
            return false;
        }
        let sum_sq: f32 = samples.iter().map(|s| s * s).sum();
        let rms = (sum_sq / samples.len() as f32).sqrt();
        rms >= self.threshold
    }
}

// ── Silero ONNX (feature-gated) ────────────────────────────────────────────

#[cfg(feature = "silero-vad")]
mod silero {
    use super::*;
    use ndarray::Array2;
    use ort::session::{Session, SessionInputValue};
    use ort::value::Tensor;
    use std::sync::Mutex;

    pub struct SileroVad {
        state: Mutex<SileroState>,
    }

    struct SileroState {
        session: Session,
        /// LSTM state tensor `[2 * 64, 1]` (h then c stacked). Updated per
        /// inference and fed back as the next call's input.
        state: Array2<f32>,
    }

    impl SileroVad {
        pub fn try_load(model_path: &Path) -> Option<Self> {
            match Self::load(model_path) {
                Ok(v) => Some(v),
                Err(e) => {
                    eprintln!(
                        "[voice/vad] Silero load failed at {}: {e} — using EnergyVad",
                        model_path.display()
                    );
                    None
                }
            }
        }

        fn load(model_path: &Path) -> Result<Self, String> {
            let session = Session::builder()
                .map_err(|e| format!("ort SessionBuilder: {e}"))?
                .commit_from_file(model_path)
                .map_err(|e| format!("ort load {}: {e}", model_path.display()))?;
            let state = Array2::<f32>::zeros((2 * 64, 1));
            Ok(Self {
                state: Mutex::new(SileroState { session, state }),
            })
        }
    }

    impl Vad for SileroVad {
        fn is_speech(&self, samples: &[f32], sample_rate: u32) -> bool {
            let mut frame = vec![0.0_f32; SILERO_FRAME];
            let n = samples.len().min(SILERO_FRAME);
            frame[..n].copy_from_slice(&samples[..n]);

            let mut guard = match self.state.lock() {
                Ok(g) => g,
                Err(p) => p.into_inner(),
            };

            let input_arr = match Array2::<f32>::from_shape_vec((1, SILERO_FRAME), frame) {
                Ok(a) => a,
                Err(_) => return false,
            };

            let input_tensor = match Tensor::from_array(input_arr) {
                Ok(t) => SessionInputValue::Owned(t.into()),
                Err(_) => return false,
            };
            let sr_tensor = match Tensor::from_array(([1_usize], vec![sample_rate as i64])) {
                Ok(t) => SessionInputValue::Owned(t.into()),
                Err(_) => return false,
            };
            let state_tensor = match Tensor::from_array(guard.state.clone()) {
                Ok(t) => SessionInputValue::Owned(t.into()),
                Err(_) => return false,
            };

            let outputs = match guard.session.run(ort::inputs![
                "input" => input_tensor,
                "sr" => sr_tensor,
                "state" => state_tensor,
            ]) {
                Ok(o) => o,
                Err(_) => return false,
            };

            if let Some(state_out) = outputs.get("stateN") {
                if let Ok((_, data)) = state_out.try_extract_tensor::<f32>() {
                    if data.len() == guard.state.len() {
                        if let Ok(new_state) =
                            Array2::<f32>::from_shape_vec(guard.state.dim(), data.to_vec())
                        {
                            guard.state = new_state;
                        }
                    }
                }
            }

            let prob = outputs
                .get("output")
                .and_then(|o| o.try_extract_tensor::<f32>().ok())
                .and_then(|(_, data)| data.first().copied())
                .unwrap_or(0.0);
            prob > 0.5
        }
    }
}

#[cfg(feature = "silero-vad")]
pub use silero::SileroVad;

// ── Factory ────────────────────────────────────────────────────────────────

/// Build the best available VAD for `model_path`. Falls back to [`EnergyVad`]
/// when the `silero-vad` feature is off, the file is missing, or ONNX load
/// fails.
#[allow(unused_variables)]
pub fn build(model_path: Option<&Path>) -> Box<dyn Vad> {
    #[cfg(feature = "silero-vad")]
    {
        if let Some(path) = model_path {
            if path.exists() {
                if let Some(silero) = SileroVad::try_load(path) {
                    return Box::new(silero);
                }
            }
        }
    }
    Box::new(EnergyVad::default())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn energy_vad_rejects_silence() {
        let vad = EnergyVad::default();
        assert!(!vad.is_speech(&vec![0.0_f32; 1600], 16_000));
    }

    #[test]
    fn energy_vad_accepts_loud() {
        let vad = EnergyVad::default();
        let buf: Vec<f32> = (0..1600).map(|i| 0.05 * ((i as f32) * 0.1).sin()).collect();
        assert!(vad.is_speech(&buf, 16_000));
    }

    #[test]
    fn build_falls_back_when_path_missing() {
        let v = build(Some(Path::new("/no/such/silero.onnx")));
        assert!(!v.is_speech(&vec![0.0_f32; 16], 16_000));
    }
}
