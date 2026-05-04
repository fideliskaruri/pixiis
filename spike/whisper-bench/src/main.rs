//! whisper-rs benchmark — Phase 0 spike for Pixiis Tauri/Rust port.
//!
//! Measures cold model load, full transcription wall time, time-to-first-token
//! (TTFB) via the new-segment callback, and peak resident set size on a single
//! WAV clip. Output is JSON on stdout so the harness can collect numbers.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Instant;

use anyhow::{Context, Result, anyhow, bail};
use clap::Parser;
use hound::{SampleFormat, WavReader};
use memory_stats::memory_stats;
use serde::Serialize;
use whisper_rs::{
    FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters,
};

#[derive(Parser, Debug)]
#[command(about = "Bench whisper-rs cold load + transcription latency")]
struct Args {
    /// Path to a GGUF/ggml whisper model (e.g. ggml-base.en.bin)
    #[arg(long)]
    model: PathBuf,

    /// Path to a WAV file (any rate / channel layout — will be downmixed + resampled)
    #[arg(long)]
    wav: PathBuf,

    /// Number of CPU threads (default: physical core count)
    #[arg(long)]
    threads: Option<i32>,

    /// Try to enable GPU (CUDA/Metal/Vulkan) — has no effect on builds without GPU features
    #[arg(long, default_value_t = false)]
    gpu: bool,

    /// Language hint (default: en)
    #[arg(long, default_value = "en")]
    language: String,

    /// Beam size — kept low for live-mode realism
    #[arg(long, default_value_t = 1)]
    beam: i32,

    /// Optional label to embed in JSON output (e.g. "base.en-cpu-int8")
    #[arg(long, default_value = "run")]
    label: String,
}

#[derive(Serialize)]
struct BenchResult<'a> {
    label: &'a str,
    model: String,
    wav: String,
    audio_seconds: f64,
    threads: i32,
    gpu_requested: bool,
    model_load_ms: f64,
    transcribe_ms: f64,
    ttfb_ms: Option<f64>,
    rss_baseline_mb: f64,
    rss_after_load_mb: f64,
    rss_peak_mb: f64,
    rss_delta_mb: f64,
    realtime_factor: f64,
    transcript: String,
}

fn rss_mb() -> f64 {
    memory_stats()
        .map(|s| s.physical_mem as f64 / (1024.0 * 1024.0))
        .unwrap_or(0.0)
}

fn read_wav_to_f32_mono_16k(path: &PathBuf) -> Result<(Vec<f32>, f64)> {
    let mut reader =
        WavReader::open(path).with_context(|| format!("opening WAV {}", path.display()))?;
    let spec = reader.spec();
    let channels = spec.channels as usize;
    let in_rate = spec.sample_rate;
    if channels == 0 {
        bail!("WAV reports 0 channels");
    }

    // Decode to interleaved f32 in [-1, 1].
    let interleaved: Vec<f32> = match (spec.sample_format, spec.bits_per_sample) {
        (SampleFormat::Int, 16) => reader
            .samples::<i16>()
            .map(|s| s.map(|v| v as f32 / 32768.0))
            .collect::<Result<Vec<_>, _>>()?,
        (SampleFormat::Int, 24) | (SampleFormat::Int, 32) => reader
            .samples::<i32>()
            .map(|s| s.map(|v| v as f32 / i32::MAX as f32))
            .collect::<Result<Vec<_>, _>>()?,
        (SampleFormat::Float, 32) => reader
            .samples::<f32>()
            .collect::<Result<Vec<_>, _>>()?,
        (fmt, bits) => bail!("unsupported WAV: {:?}/{}", fmt, bits),
    };

    // Downmix to mono.
    let mono: Vec<f32> = if channels == 1 {
        interleaved
    } else {
        let inv = 1.0 / channels as f32;
        interleaved
            .chunks_exact(channels)
            .map(|frame| frame.iter().sum::<f32>() * inv)
            .collect()
    };

    // Resample to 16 kHz with cheap linear interpolation. The bench is for
    // wall-clock; we don't need a polyphase filter to validate latency targets.
    let mono_16k: Vec<f32> = if in_rate == 16_000 {
        mono
    } else {
        linear_resample(&mono, in_rate, 16_000)
    };

    let secs = mono_16k.len() as f64 / 16_000.0;
    Ok((mono_16k, secs))
}

fn linear_resample(input: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
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

fn main() -> Result<()> {
    let args = Args::parse();

    let rss_baseline = rss_mb();

    // --- Decode audio ----------------------------------------------------
    let (samples, audio_seconds) = read_wav_to_f32_mono_16k(&args.wav)?;
    if samples.is_empty() {
        bail!("decoded zero audio samples");
    }

    // --- Cold model load -------------------------------------------------
    let mut ctx_params = WhisperContextParameters::default();
    ctx_params.use_gpu = args.gpu;

    let model_path = args
        .model
        .to_str()
        .ok_or_else(|| anyhow!("model path is not valid UTF-8"))?;

    let load_start = Instant::now();
    let ctx = WhisperContext::new_with_params(model_path, ctx_params)
        .with_context(|| format!("loading model {}", args.model.display()))?;
    let model_load_ms = load_start.elapsed().as_secs_f64() * 1000.0;
    let rss_after_load = rss_mb();

    let mut state = ctx.create_state().context("creating WhisperState")?;

    // --- Transcribe params ----------------------------------------------
    let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: args.beam });
    let threads = args.threads.unwrap_or_else(|| {
        std::thread::available_parallelism()
            .map(|n| n.get() as i32)
            .unwrap_or(4)
    });
    params.set_n_threads(threads);
    params.set_language(Some(&args.language));
    params.set_print_progress(false);
    params.set_print_realtime(false);
    params.set_print_special(false);
    params.set_print_timestamps(false);
    params.set_translate(false);
    params.set_suppress_blank(true);

    // --- TTFB capture via new-segment callback --------------------------
    let transcribe_start = Arc::new(Instant::now());
    let ttfb: Arc<Mutex<Option<f64>>> = Arc::new(Mutex::new(None));
    {
        let ttfb_cb = Arc::clone(&ttfb);
        let start_cb = Arc::clone(&transcribe_start);
        params.set_new_segment_callback_safe(move |_n_new: i32| {
            let mut slot = ttfb_cb.lock().unwrap();
            if slot.is_none() {
                *slot = Some(start_cb.elapsed().as_secs_f64() * 1000.0);
            }
        });
    }

    // --- Run -------------------------------------------------------------
    let _t0 = Instant::now(); // already captured in transcribe_start
    let run_start = Instant::now();
    state.full(params, &samples).context("whisper full() failed")?;
    let transcribe_ms = run_start.elapsed().as_secs_f64() * 1000.0;
    let rss_peak = rss_mb();

    // --- Pull transcript text -------------------------------------------
    let mut transcript = String::new();
    let n_segments = state.full_n_segments().unwrap_or(0);
    for i in 0..n_segments {
        if let Ok(seg) = state.full_get_segment_text(i) {
            transcript.push_str(seg.trim());
            transcript.push(' ');
        }
    }
    let transcript = transcript.trim().to_string();

    // --- Report ----------------------------------------------------------
    let ttfb_ms = *ttfb.lock().unwrap();
    let result = BenchResult {
        label: &args.label,
        model: args.model.display().to_string(),
        wav: args.wav.display().to_string(),
        audio_seconds,
        threads,
        gpu_requested: args.gpu,
        model_load_ms,
        transcribe_ms,
        ttfb_ms,
        rss_baseline_mb: rss_baseline,
        rss_after_load_mb: rss_after_load,
        rss_peak_mb: rss_peak,
        rss_delta_mb: rss_peak - rss_baseline,
        realtime_factor: if audio_seconds > 0.0 {
            (transcribe_ms / 1000.0) / audio_seconds
        } else {
            0.0
        },
        transcript,
    };

    println!("{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}
