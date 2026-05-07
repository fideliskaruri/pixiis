//! Microphone capture via cpal. Always normalises to **16 kHz mono f32**
//! before handing samples to the pipeline, so downstream code (VAD, whisper)
//! never has to think about device rate / channel count.
//!
//! Port of `audio_capture.py`. The Python sounddevice version asked the OS
//! for 16 kHz int16 directly; cpal exposes whatever the default config is,
//! so we downmix + resample in the data callback. The resampler is the same
//! cheap linear interpolator the whisper-bench spike uses — fine for ASR.

use std::sync::Arc;
use std::thread;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{InputCallbackInfo, SampleFormat, StreamConfig};
use crossbeam_channel::{bounded, Sender};

use crate::error::{AppError, AppResult};
use crate::types::VoiceDevice;

pub const TARGET_SAMPLE_RATE: u32 = 16_000;

/// Owns one running cpal input stream. Drop / [`Self::stop`] tears it down.
pub struct AudioCapture {
    stop_tx: Sender<()>,
    handle: Option<thread::JoinHandle<()>>,
}

impl AudioCapture {
    /// Open the named device (or the default if `None`) and call
    /// `on_samples` with each chunk of 16 kHz mono f32 audio.
    pub fn start<F>(device_name: Option<&str>, on_samples: F) -> AppResult<Self>
    where
        F: Fn(Vec<f32>) + Send + Sync + 'static,
    {
        let device_name = device_name.map(str::to_owned);
        let on_samples = Arc::new(on_samples);

        // Stream is `!Send` on Windows — own it on a dedicated thread and
        // signal teardown over a one-shot channel.
        let (stop_tx, stop_rx) = bounded::<()>(1);
        let (ready_tx, ready_rx) = bounded::<AppResult<()>>(1);

        let handle = thread::Builder::new()
            .name("voice-capture".into())
            .spawn(move || {
                let host = cpal::default_host();

                let device_result = match device_name.as_deref() {
                    None => host
                        .default_input_device()
                        .ok_or_else(|| AppError::Other("no default input device".into())),
                    Some(name) => host
                        .input_devices()
                        .map_err(|e| AppError::Other(format!("cpal input_devices: {e}")))
                        .and_then(|mut iter| {
                            iter.find(|d| d.name().ok().as_deref() == Some(name))
                                .ok_or_else(|| {
                                    AppError::NotFound(format!("input device {name}"))
                                })
                        }),
                };

                let device = match device_result {
                    Ok(d) => d,
                    Err(e) => {
                        let _ = ready_tx.send(Err(e));
                        return;
                    }
                };

                let supported = match device.default_input_config() {
                    Ok(c) => c,
                    Err(e) => {
                        let _ = ready_tx.send(Err(AppError::Other(format!(
                            "cpal default_input_config: {e}"
                        ))));
                        return;
                    }
                };

                let in_rate = supported.sample_rate().0;
                let in_channels = supported.channels() as usize;
                let format = supported.sample_format();
                let config: StreamConfig = supported.into();

                let cb = on_samples.clone();
                let stream_result = match format {
                    SampleFormat::F32 => device.build_input_stream(
                        &config,
                        move |data: &[f32], _: &InputCallbackInfo| {
                            let mono = downmix(data, in_channels);
                            let resampled = resample_linear(&mono, in_rate, TARGET_SAMPLE_RATE);
                            if !resampled.is_empty() {
                                cb(resampled);
                            }
                        },
                        |err| eprintln!("[voice] cpal stream error: {err}"),
                        None,
                    ),
                    SampleFormat::I16 => device.build_input_stream(
                        &config,
                        move |data: &[i16], _: &InputCallbackInfo| {
                            let f32_buf: Vec<f32> =
                                data.iter().map(|s| *s as f32 / 32768.0).collect();
                            let mono = downmix(&f32_buf, in_channels);
                            let resampled = resample_linear(&mono, in_rate, TARGET_SAMPLE_RATE);
                            if !resampled.is_empty() {
                                cb(resampled);
                            }
                        },
                        |err| eprintln!("[voice] cpal stream error: {err}"),
                        None,
                    ),
                    SampleFormat::U16 => device.build_input_stream(
                        &config,
                        move |data: &[u16], _: &InputCallbackInfo| {
                            let f32_buf: Vec<f32> = data
                                .iter()
                                .map(|s| (*s as f32 - 32768.0) / 32768.0)
                                .collect();
                            let mono = downmix(&f32_buf, in_channels);
                            let resampled = resample_linear(&mono, in_rate, TARGET_SAMPLE_RATE);
                            if !resampled.is_empty() {
                                cb(resampled);
                            }
                        },
                        |err| eprintln!("[voice] cpal stream error: {err}"),
                        None,
                    ),
                    other => {
                        let _ = ready_tx.send(Err(AppError::Other(format!(
                            "unsupported cpal sample format: {other:?}"
                        ))));
                        return;
                    }
                };

                let stream = match stream_result {
                    Ok(s) => s,
                    Err(e) => {
                        let _ = ready_tx.send(Err(AppError::Other(format!(
                            "cpal build_input_stream: {e}"
                        ))));
                        return;
                    }
                };

                if let Err(e) = stream.play() {
                    let _ = ready_tx.send(Err(AppError::Other(format!("cpal play: {e}"))));
                    return;
                }

                let _ = ready_tx.send(Ok(()));
                let _ = stop_rx.recv(); // block until told to tear down
                drop(stream); // pause + close
            })
            .map_err(|e| AppError::Other(format!("spawn capture thread: {e}")))?;

        // Propagate the stream-open result before returning success.
        match ready_rx.recv() {
            Ok(Ok(())) => Ok(Self {
                stop_tx,
                handle: Some(handle),
            }),
            Ok(Err(e)) => {
                let _ = stop_tx.send(());
                let _ = handle.join();
                Err(e)
            }
            Err(_) => {
                let _ = handle.join();
                Err(AppError::Other("capture thread vanished".into()))
            }
        }
    }

    pub fn stop(mut self) {
        let _ = self.stop_tx.send(());
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

impl Drop for AudioCapture {
    fn drop(&mut self) {
        let _ = self.stop_tx.send(());
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
    }
}

/// Enumerate input devices for the Settings UI.
pub fn list_devices() -> AppResult<Vec<VoiceDevice>> {
    let host = cpal::default_host();
    let default_name = host
        .default_input_device()
        .and_then(|d| d.name().ok())
        .unwrap_or_default();

    let mut out = Vec::new();
    let devices = host
        .input_devices()
        .map_err(|e| AppError::Other(format!("cpal input_devices: {e}")))?;
    for d in devices {
        if let Ok(name) = d.name() {
            let is_default = name == default_name;
            out.push(VoiceDevice {
                id: name.clone(),
                name,
                is_default,
            });
        }
    }
    Ok(out)
}

fn downmix(interleaved: &[f32], channels: usize) -> Vec<f32> {
    if channels <= 1 {
        return interleaved.to_vec();
    }
    let inv = 1.0 / channels as f32;
    interleaved
        .chunks_exact(channels)
        .map(|frame| frame.iter().sum::<f32>() * inv)
        .collect()
}

/// Cheap linear-interpolation resampler. Sufficient for ASR — whisper.cpp's
/// own front-end is forgiving — and avoids dragging in a polyphase library.
fn resample_linear(input: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if input.is_empty() || from_rate == to_rate {
        return input.to_vec();
    }
    let ratio = from_rate as f64 / to_rate as f64;
    let out_len = (input.len() as f64 / ratio).round() as usize;
    let mut out = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let src = i as f64 * ratio;
        let lo = src.floor() as usize;
        let hi = (lo + 1).min(input.len() - 1);
        let frac = (src - lo as f64) as f32;
        out.push(input[lo] * (1.0 - frac) + input[hi] * frac);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn downmix_stereo_to_mono() {
        let stereo = [1.0_f32, -1.0, 0.5, 0.5, 0.0, 1.0];
        let mono = downmix(&stereo, 2);
        assert_eq!(mono, vec![0.0, 0.5, 0.5]);
    }

    #[test]
    fn downmix_mono_passthrough() {
        let mono_in = [0.1_f32, 0.2, 0.3];
        assert_eq!(downmix(&mono_in, 1), mono_in.to_vec());
    }

    #[test]
    fn resample_passthrough_when_same_rate() {
        let buf = vec![0.1_f32, 0.2, 0.3, 0.4];
        assert_eq!(resample_linear(&buf, 16_000, 16_000), buf);
    }

    #[test]
    fn resample_downsamples_48k_to_16k() {
        let buf: Vec<f32> = (0..4800).map(|i| i as f32 / 4800.0).collect();
        let out = resample_linear(&buf, 48_000, 16_000);
        // 1/3 the samples ± rounding.
        assert!((out.len() as i64 - 1600).abs() <= 1, "got {}", out.len());
    }
}
