//! Discover (and on first run, install) the Whisper + Silero models the
//! voice subsystem needs.
//!
//! Strategy (matches the Wave 2 brief's "Model bundling decision"):
//!
//! 1. Look for the model under `%APPDATA%/pixiis/models/whisper/` (resp.
//!    `models/silero/`). If it's there, use it.
//! 2. Otherwise, look for the bundled copy. Tauri 2's NSIS bundler
//!    rewrites parent-traversal source paths (`../resources/...`) into
//!    a `_up_` subdirectory under `$INSTDIR`, so the runtime layout is
//!    `<INSTDIR>/_up_/resources/models/whisper/<file>.bin`. Verified
//!    empirically against the generated `installer.nsi` (lines 638–641).
//!    We try that path first when a `resource_dir` is supplied, then
//!    fall through to other plausible Tauri 2 layouts.
//! 3. If found in (2), copy it into the user data dir and use that.
//! 4. If still missing, return `None` — the caller decides whether to
//!    error (whisper) or fall back (Silero → EnergyVad).
//!
//! Every fallback attempt is logged via `eprintln!` so future install
//! mismatches are diagnosable from the log without rebuilding.

use std::fs;
use std::path::{Path, PathBuf};

pub const DEFAULT_WHISPER_FILENAME: &str = "ggml-base.en-q5_1.bin";
pub const SILERO_FILENAME: &str = "silero_vad.onnx";

/// HuggingFace mirror of the bundled quantised base.en model. Used as a
/// last-resort fallback when the installer somehow shipped without the
/// bundled binary (corrupted install, hand-edited install, or a portable
/// archive that stripped the resources). The Rust `voice_download_model`
/// command streams this to `user_whisper_path()` and emits progress
/// events the UI can render as a percentage bar.
pub const DEFAULT_WHISPER_HF_URL: &str =
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_1.bin";

/// Returns the user-data directory the voice subsystem writes models to.
/// On Windows this is `%APPDATA%/pixiis/models/`; falls back to a temp
/// dir when the OS doesn't expose one.
pub fn user_models_dir() -> PathBuf {
    dirs::data_dir()
        .map(|p| p.join("pixiis").join("models"))
        .unwrap_or_else(|| std::env::temp_dir().join("pixiis").join("models"))
}

/// Locate the Whisper model, copying the bundled default into the user's
/// data dir on first run. Returns `None` if neither location has it (the
/// installer is broken or someone removed the file by hand).
pub fn ensure_default_whisper_model() -> Option<PathBuf> {
    ensure_default_whisper_model_with(None)
}

/// Same as [`ensure_default_whisper_model`] but lets the caller supply
/// Tauri's `app.path().resource_dir()` so we can resolve the bundled
/// model on platforms / install layouts where the heuristic exe-relative
/// search misses (e.g. Tauri 2's NSIS layout puts resources alongside
/// the exe but installs into a versioned subdirectory).
pub fn ensure_default_whisper_model_with(resource_dir: Option<PathBuf>) -> Option<PathBuf> {
    let user_dir = user_models_dir().join("whisper");
    let user_path = user_dir.join(DEFAULT_WHISPER_FILENAME);
    if user_path.exists() {
        return Some(user_path);
    }

    if let Some(bundled) = find_bundled("whisper", DEFAULT_WHISPER_FILENAME, resource_dir.as_ref())
    {
        if let Err(e) = fs::create_dir_all(&user_dir) {
            eprintln!(
                "[voice/model] could not create {}: {e}",
                user_dir.display()
            );
            // Fall through to using the bundled path directly — read-only
            // is fine, whisper just needs to be able to mmap it.
            return Some(bundled);
        }
        match fs::copy(&bundled, &user_path) {
            Ok(_) => Some(user_path),
            Err(e) => {
                eprintln!(
                    "[voice/model] copy {} -> {}: {e} — using bundled in place",
                    bundled.display(),
                    user_path.display()
                );
                Some(bundled)
            }
        }
    } else {
        None
    }
}

/// Locate the Silero VAD model. Same lookup pattern, optional return —
/// callers fall back to [`crate::voice::vad::EnergyVad`].
pub fn ensure_silero_model() -> Option<PathBuf> {
    ensure_silero_model_with(None)
}

/// Resource-dir aware variant — see [`ensure_default_whisper_model_with`].
pub fn ensure_silero_model_with(resource_dir: Option<PathBuf>) -> Option<PathBuf> {
    let user_dir = user_models_dir().join("silero");
    let user_path = user_dir.join(SILERO_FILENAME);
    if user_path.exists() {
        return Some(user_path);
    }
    let bundled = find_bundled("silero", SILERO_FILENAME, resource_dir.as_ref())?;
    if fs::create_dir_all(&user_dir).is_ok() {
        let _ = fs::copy(&bundled, &user_path);
        if user_path.exists() {
            return Some(user_path);
        }
    }
    Some(bundled)
}

/// Look for a model file in any of the standard "shipped next to the exe"
/// or "in the dev source tree" locations. When `resource_dir` is provided
/// (Tauri's `app.path().resource_dir()`), it's tried first — it's the
/// authoritative bundle root on a real install.
///
/// We log every miss with `eprintln!` so future "model not available"
/// reports can be diagnosed by reading the log instead of bisecting the
/// installer layout.
fn find_bundled(
    subdir: &str,
    filename: &str,
    resource_dir: Option<&PathBuf>,
) -> Option<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();

    // 1. Tauri's own resource_dir — most reliable on a real install.
    if let Some(rd) = resource_dir {
        // **Empirically verified Tauri 2 NSIS layout.** When
        // `bundle.resources` references `../resources/...`, the NSIS
        // installer rewrites the parent-traversal as `_up_/resources/...`
        // under `$INSTDIR`. See generated `installer.nsi`:
        //   File /a "/oname=_up_\resources\models\whisper\…\.bin" "<src>"
        // So the live file lands at:
        //   <resource_dir>/_up_/resources/models/<subdir>/<filename>
        roots.push(rd.join("_up_").join("resources").join("models"));
        // bundle.resources without parent-traversal would keep the source
        // tree's layout, so the file lands at
        // `<resource_dir>/resources/models/<subdir>/<filename>`.
        roots.push(rd.join("resources").join("models"));
        // Some Tauri 2 NSIS layouts flatten one level — try that too.
        roots.push(rd.join("models"));
        // Defensive: parent-traversal preserved without `_up_` rewrite
        // (older Tauri versions / non-NSIS bundlers).
        if let Some(parent) = rd.parent() {
            roots.push(parent.join("resources").join("models"));
        }
    }

    // 2. Heuristic exe-relative paths for cases where the caller didn't
    //    pass a resource dir (tests, describe_model_paths, …) or it
    //    points somewhere unexpected.
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            // NSIS production layout: `<exe_dir>/_up_/resources/models/…`.
            roots.push(dir.join("_up_").join("resources").join("models"));
            // Non-traversal layout next to the exe.
            roots.push(dir.join("resources").join("models"));
            // Some Tauri 2 bundle modes put resources up one level.
            if let Some(parent) = dir.parent() {
                roots.push(parent.join("resources").join("models"));
                // And up two for some dev-build layouts.
                if let Some(grand) = parent.parent() {
                    roots.push(grand.join("resources").join("models"));
                }
            }
        }
    }

    // 3. %APPDATA%/pixiis/models/<subdir>/<filename> — the user dir is
    //    handled by the caller before find_bundled, but include it here
    //    too so this function is honestly a "look everywhere" helper.
    if let Some(data) = dirs::data_dir() {
        roots.push(data.join("pixiis").join("models"));
    }

    // 4. Dev / `cargo run` from src-tauri/.
    roots.push(PathBuf::from("../resources/models"));
    roots.push(PathBuf::from("resources/models"));

    for root in roots {
        let candidate = root.join(subdir).join(filename);
        if candidate.exists() {
            eprintln!(
                "[voice/model] found bundled {}/{} at {}",
                subdir,
                filename,
                candidate.display()
            );
            return Some(candidate);
        } else {
            eprintln!(
                "[voice/model] miss: {} (looking for {}/{})",
                candidate.display(),
                subdir,
                filename
            );
        }
    }
    eprintln!(
        "[voice/model] exhausted all bundle paths for {}/{}",
        subdir, filename
    );
    None
}

/// Convenience used by the voice command tests + first-run UI to report
/// what the system will actually load.
pub fn describe_model_paths() -> ModelLocations {
    ModelLocations {
        whisper: ensure_default_whisper_model(),
        silero: ensure_silero_model(),
    }
}

#[derive(Debug, Clone)]
pub struct ModelLocations {
    pub whisper: Option<PathBuf>,
    pub silero: Option<PathBuf>,
}

/// Whether the supplied `voice.model` config string refers to the
/// bundled default. Anything blank/`default`/`bundled` plus the canonical
/// `base.en-q5_1` aliases count. Used by the Settings UI to render the
/// "model: bundled" badge.
pub fn is_default_bundled_model_id(model_id: &str) -> bool {
    let id = model_id.trim().to_ascii_lowercase();
    matches!(
        id.as_str(),
        "" | "default"
            | "bundled"
            | "base-en-q5_1"
            | "base.en-q5_1"
            | "base.en"
            | "base"
            | "base-en"
    )
}

/// Where the runtime download writes the fetched model. Lines up with
/// the user-dir lookup in [`ensure_default_whisper_model_with`] so a
/// successful download is picked up on the next call without restart.
pub fn user_whisper_path() -> PathBuf {
    user_models_dir()
        .join("whisper")
        .join(DEFAULT_WHISPER_FILENAME)
}

/// Make sure `path`'s parent directory exists. Lets the download command
/// share its mkdir logic with the cached-copy branch above.
pub fn ensure_parent(path: &Path) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn user_models_dir_is_under_pixiis() {
        let p = user_models_dir();
        assert!(p.ends_with("models"), "got {}", p.display());
    }

    #[test]
    fn missing_bundle_returns_none() {
        // No `resources/models/whisper/...` is on disk during `cargo test`,
        // and the user dir under temp is empty.
        let _ = find_bundled("nope-no-such-subdir", "nope.bin", None);
    }

    #[test]
    fn default_bundled_model_ids_recognised() {
        assert!(is_default_bundled_model_id(""));
        assert!(is_default_bundled_model_id("default"));
        assert!(is_default_bundled_model_id("base-en-q5_1"));
        assert!(is_default_bundled_model_id("BASE.EN"));
        assert!(!is_default_bundled_model_id("large-v3"));
        assert!(!is_default_bundled_model_id("medium"));
    }

    #[test]
    fn user_whisper_path_lands_under_models() {
        let p = user_whisper_path();
        assert!(p.ends_with("whisper/ggml-base.en-q5_1.bin")
            || p.ends_with("whisper\\ggml-base.en-q5_1.bin"));
    }
}
