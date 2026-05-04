//! Kokoro-onnx → ort 2.0 spike benchmark.
//!
//! Validates that Kokoro v1.0 TTS can run in pure Rust via the `ort` crate
//! with byte-equivalent output to the Python `kokoro-onnx` reference.
//!
//! Pipeline (mirrors kokoro_onnx.Kokoro.create):
//!   text → espeak-ng IPA → vocab filter → token IDs → ORT inference → f32 audio @ 24kHz

mod espeak;
mod vocab;
mod voices;

use anyhow::{bail, Context, Result};
use clap::Parser;
use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Value;
use std::path::PathBuf;
use std::time::Instant;

const SAMPLE_RATE: u32 = 24_000;
const MAX_PHONEME_LENGTH: usize = 510;

#[derive(Parser, Debug)]
#[command(version, about = "Kokoro-onnx Rust ort 2.0 benchmark")]
struct Args {
    /// Path to kokoro-v1.0.onnx
    #[arg(long)]
    model: PathBuf,
    /// Path to voices-v1.0.bin
    #[arg(long)]
    voices: PathBuf,
    /// Voice name (e.g. am_michael).
    #[arg(long, default_value = "am_michael")]
    voice: String,
    /// Plain text input (gets phonemized via espeak-ng).
    #[arg(long, conflicts_with = "phonemes")]
    text: Option<String>,
    /// Pre-computed phoneme string (skips phonemizer for byte-equivalence test).
    #[arg(long, conflicts_with = "text")]
    phonemes: Option<String>,
    /// Path to libespeak-ng.so (auto-detect from kokoro_onnx if omitted).
    #[arg(long)]
    espeak_lib: Option<PathBuf>,
    /// Path to espeak-ng-data dir.
    #[arg(long)]
    espeak_data: Option<PathBuf>,
    /// Output WAV path.
    #[arg(long)]
    out: PathBuf,
    /// Speech speed (0.5 .. 2.0).
    #[arg(long, default_value_t = 1.0)]
    speed: f32,
    /// Try CUDA execution provider; fall back to CPU on failure.
    #[arg(long)]
    cuda: bool,
    /// Print emitted phonemes to stdout (debug).
    #[arg(long)]
    print_phonemes: bool,
}

fn main() -> Result<()> {
    let args = Args::parse();

    if !(0.5..=2.0).contains(&args.speed) {
        bail!("--speed must be in [0.5, 2.0]");
    }

    // ── stage 1: load model ────────────────────────────────────────────────
    let t_load = Instant::now();
    ort::init().commit()?;
    let mut session_builder = Session::builder()?
        .with_optimization_level(GraphOptimizationLevel::Level3)?
        .with_intra_threads(num_cpus::get_physical().max(1).min(8))?;
    let provider_used: &'static str = if args.cuda {
        match ort::execution_providers::CUDAExecutionProvider::default()
            .with_device_id(0)
            .build()
            .error_on_failure()
        {
            ep => {
                session_builder = session_builder.with_execution_providers([ep])?;
                "CUDA"
            }
        }
    } else {
        "CPU"
    };
    let mut session = session_builder
        .commit_from_file(&args.model)
        .with_context(|| format!("load model {}", args.model.display()))?;
    let load_ms = t_load.elapsed().as_secs_f64() * 1000.0;

    // ── stage 2: load voices ───────────────────────────────────────────────
    let t_voices = Instant::now();
    let voices = voices::Voices::load(&args.voices)?;
    let voices_ms = t_voices.elapsed().as_secs_f64() * 1000.0;

    // ── stage 3: vocab + tokens ────────────────────────────────────────────
    let vocab = vocab::Vocab::embedded()?;

    let phonemes_str = match (&args.text, &args.phonemes) {
        (Some(text), None) => {
            let lib_path = args.espeak_lib.clone().unwrap_or_else(default_espeak_lib);
            let data_path = args.espeak_data.clone().unwrap_or_else(default_espeak_data);
            let espeak = espeak::EspeakNg::load(&lib_path, &data_path)
                .context("loading espeak-ng (try --espeak-lib / --espeak-data)")?;
            let raw = espeak.phonemize(text.trim())?;
            if args.print_phonemes {
                eprintln!("raw phonemes: {raw:?}");
            }
            vocab.filter(&raw)
        }
        (None, Some(phonemes)) => phonemes.clone(),
        _ => bail!("supply exactly one of --text or --phonemes"),
    };

    if args.print_phonemes {
        eprintln!("phonemes: {phonemes_str:?}");
    }

    if phonemes_str.chars().count() > MAX_PHONEME_LENGTH {
        bail!(
            "phoneme string too long ({} > {})",
            phonemes_str.chars().count(),
            MAX_PHONEME_LENGTH
        );
    }

    let mut tokens = vocab.tokenize(&phonemes_str);
    let token_count_for_style = tokens.len();
    // pad: prepend & append 0
    tokens.insert(0, 0);
    tokens.push(0);

    // ── stage 4: gather style ──────────────────────────────────────────────
    let style_slice = voices.style_for(&args.voice, token_count_for_style)?.to_vec();

    // ── stage 5: ORT inference ─────────────────────────────────────────────
    let t_infer = Instant::now();

    let token_count = tokens.len();
    let tokens_arr =
        ndarray::Array2::<i64>::from_shape_vec((1, token_count), tokens)?;
    let style_arr = ndarray::Array2::<f32>::from_shape_vec((1, 256), style_slice)?;
    let speed_arr = ndarray::Array1::<f32>::from_vec(vec![args.speed]);

    let inputs = ort::inputs! {
        "tokens" => Value::from_array(tokens_arr)?,
        "style" => Value::from_array(style_arr)?,
        "speed" => Value::from_array(speed_arr)?,
    };

    let outputs = session.run(inputs)?;
    let infer_ms = t_infer.elapsed().as_secs_f64() * 1000.0;

    let audio_value = outputs
        .iter()
        .next()
        .context("model returned no outputs")?
        .1;
    let (_shape, audio_data) = audio_value.try_extract_tensor::<f32>()?;
    let audio: Vec<f32> = audio_data.to_vec();
    let duration_s = audio.len() as f64 / SAMPLE_RATE as f64;

    // ── stage 6: write WAV ─────────────────────────────────────────────────
    let t_write = Instant::now();
    write_wav_f32(&args.out, &audio, SAMPLE_RATE)?;
    let write_ms = t_write.elapsed().as_secs_f64() * 1000.0;

    // ── report ─────────────────────────────────────────────────────────────
    let report = serde_json::json!({
        "provider": provider_used,
        "phonemes": phonemes_str,
        "phoneme_count": phonemes_str.chars().count(),
        "token_count": token_count,
        "audio_samples": audio.len(),
        "audio_duration_s": duration_s,
        "model_load_ms": load_ms,
        "voices_load_ms": voices_ms,
        "inference_ms": infer_ms,
        "wav_write_ms": write_ms,
        "rtf": infer_ms / 1000.0 / duration_s.max(1e-9),
        "out_path": args.out.display().to_string(),
    });
    println!("{}", serde_json::to_string_pretty(&report)?);
    Ok(())
}

fn write_wav_f32(path: &std::path::Path, samples: &[f32], sample_rate: u32) -> Result<()> {
    let spec = hound::WavSpec {
        channels: 1,
        sample_rate,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mut writer = hound::WavWriter::create(path, spec)
        .with_context(|| format!("create wav {}", path.display()))?;
    for s in samples {
        writer.write_sample(*s)?;
    }
    writer.finalize()?;
    Ok(())
}

fn default_espeak_lib() -> PathBuf {
    // Default: the bundled libespeak-ng.so from the `espeakng_loader` Python
    // package. If you don't have Python kokoro-onnx installed, pass --espeak-lib.
    let candidates = [
        "/home/fwachira/.local/lib/python3.12/site-packages/espeakng_loader/libespeak-ng.so",
        "/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1",
        "/usr/lib/libespeak-ng.so.1",
    ];
    for c in candidates {
        if std::path::Path::new(c).exists() {
            return PathBuf::from(c);
        }
    }
    PathBuf::from("libespeak-ng.so")
}

fn default_espeak_data() -> PathBuf {
    let candidates = [
        "/home/fwachira/.local/lib/python3.12/site-packages/espeakng_loader/espeak-ng-data",
        "/usr/share/espeak-ng-data",
        "/usr/lib/x86_64-linux-gnu/espeak-ng-data",
    ];
    for c in candidates {
        if std::path::Path::new(c).exists() {
            return PathBuf::from(c);
        }
    }
    PathBuf::from("espeak-ng-data")
}
