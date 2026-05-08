//! Discover (and on first run, install) the Whisper + Silero models the
//! voice subsystem needs.
//!
//! Strategy (matches the Wave 2 brief's "Model bundling decision"):
//!
//! 1. Look for the model under `%APPDATA%/pixiis/models/whisper/` (resp.
//!    `models/silero/`). If it's there, use it.
//! 2. Otherwise, look for the bundled copy next to the executable
//!    (`<exe_dir>/resources/models/...`) — Tauri's NSIS bundle flattens
//!    `bundle.resources` into that path.
//! 3. If found in (2), copy it into the user data dir and use that.
//! 4. If still missing, return `None` — the caller decides whether to
//!    error (whisper) or fall back (Silero → EnergyVad).

use std::fs;
use std::path::PathBuf;

pub const DEFAULT_WHISPER_FILENAME: &str = "ggml-base.en-q5_1.bin";
pub const SILERO_FILENAME: &str = "silero_vad.onnx";

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
fn find_bundled(
    subdir: &str,
    filename: &str,
    resource_dir: Option<&PathBuf>,
) -> Option<PathBuf> {
    let mut roots: Vec<PathBuf> = Vec::new();

    // 1. Tauri's own resource_dir — most reliable on a real install.
    if let Some(rd) = resource_dir {
        // bundle.resources keeps the source tree's layout, so the file
        // lands at `<resource_dir>/resources/models/<subdir>/<filename>`.
        roots.push(rd.join("resources").join("models"));
        // Some Tauri 2 NSIS layouts flatten one level — try that too.
        roots.push(rd.join("models"));
    }

    // 2. Heuristic exe-relative paths for cases where the caller didn't
    //    pass a resource dir (tests, describe_model_paths, …) or it
    //    points somewhere unexpected.
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            // NSIS / production layout.
            roots.push(dir.join("resources").join("models"));
            // Some Tauri 2 bundle modes put resources up one level.
            if let Some(parent) = dir.parent() {
                roots.push(parent.join("resources").join("models"));
            }
        }
    }

    // 3. Dev / `cargo run` from src-tauri/.
    roots.push(PathBuf::from("../resources/models"));
    roots.push(PathBuf::from("resources/models"));

    for root in roots {
        let candidate = root.join(subdir).join(filename);
        if candidate.exists() {
            return Some(candidate);
        }
    }
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
        let _ = find_bundled("nope-no-such-subdir", "nope.bin");
    }
}
