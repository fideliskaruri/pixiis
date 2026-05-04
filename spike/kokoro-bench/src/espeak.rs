//! Minimal FFI wrapper around `libespeak-ng.so` for text → IPA phonemes.
//!
//! Loads the library at runtime via `libloading` (no static link, no build-time
//! header), reproducing the path that `phonemizer-fork` takes in Python. This
//! does NOT replicate phonemizer-fork's full punctuation-preservation logic;
//! divergences vs. the Python pipeline are documented in RESULTS.md.

use anyhow::{bail, Context, Result};
use libloading::{Library, Symbol};
use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int, c_void};
use std::path::Path;

/// `espeak_AUDIO_OUTPUT::AUDIO_OUTPUT_SYNCHRONOUS = 2` would generate audio.
/// We use `AUDIO_OUTPUT_RETRIEVAL = 0` is fine but we don't care — passing
/// any value works because we only call `espeak_TextToPhonemes`. We use 0.
const AUDIO_OUTPUT_RETRIEVAL: c_int = 0;

/// `espeakINITIALIZE_DONT_EXIT = 0x8000` — prevent espeak-ng from calling
/// exit() on errors.
const ESPEAK_INIT_DONT_EXIT: c_int = 0x8000;

/// `espeakCHARS_UTF8 = 1` for textmode arg.
const ESPEAK_CHARS_UTF8: c_int = 1;

/// `phonememode` per modern espeak-ng/include/espeak-ng/speak_lib.h:
///   bit 0       use tie character (U+0361) inside multi-letter phonemes
///   bit 1       produce IPA phonemes (Unicode); else ASCII Kirshenbaum-like
///   bits 8-23   UTF-32 codepoint separator between phonemes (0 = no sep)
/// Stress markers (ˈ ˌ) are intrinsic to IPA output and we want no separator
/// so the chars feed straight into Kokoro's vocab lookup.
const PHONEMEMODE_IPA: c_int = 0x02;

pub struct EspeakNg {
    _lib: Library,
    text_to_phonemes:
        unsafe extern "C" fn(*mut *const c_void, c_int, c_int) -> *const c_char,
    initialized: bool,
}

impl EspeakNg {
    pub fn load(lib_path: &Path, data_path: &Path) -> Result<Self> {
        let lib = unsafe { Library::new(lib_path) }
            .with_context(|| format!("dlopen {}", lib_path.display()))?;

        unsafe {
            // int espeak_Initialize(int output, int buflength, const char *path, int options);
            let init: Symbol<
                unsafe extern "C" fn(c_int, c_int, *const c_char, c_int) -> c_int,
            > = lib.get(b"espeak_Initialize\0")?;
            let cdata = CString::new(
                data_path
                    .parent()
                    .unwrap_or(data_path)
                    .to_string_lossy()
                    .as_bytes(),
            )?;
            // Buf length is in ms — 0 picks the default (200ms). Doesn't matter for phonemes.
            let rate = init(
                AUDIO_OUTPUT_RETRIEVAL,
                0,
                cdata.as_ptr(),
                ESPEAK_INIT_DONT_EXIT,
            );
            if rate == -1 {
                bail!("espeak_Initialize failed");
            }

            // espeak_ERROR espeak_SetVoiceByName(const char *name);
            let set_voice: Symbol<unsafe extern "C" fn(*const c_char) -> c_int> =
                lib.get(b"espeak_SetVoiceByName\0")?;
            let voice = CString::new("en-us")?;
            let err = set_voice(voice.as_ptr());
            if err != 0 {
                bail!("espeak_SetVoiceByName(en-us) returned {err}");
            }

            // const char* espeak_TextToPhonemes(const void **textptr, int textmode, int phonememode);
            let text_to_phonemes: Symbol<
                unsafe extern "C" fn(*mut *const c_void, c_int, c_int) -> *const c_char,
            > = lib.get(b"espeak_TextToPhonemes\0")?;
            let text_to_phonemes_fn = *text_to_phonemes.into_raw();

            Ok(Self {
                _lib: lib,
                text_to_phonemes: text_to_phonemes_fn,
                initialized: true,
            })
        }
    }

    /// Phonemize one chunk of UTF-8 text. Returns concatenated IPA phonemes.
    pub fn phonemize(&self, text: &str) -> Result<String> {
        if !self.initialized {
            bail!("espeak-ng not initialized");
        }
        let cstr = CString::new(text)?;
        let mut ptr: *const c_void = cstr.as_ptr() as *const c_void;
        let mut out = String::new();
        unsafe {
            // espeak_TextToPhonemes consumes text incrementally; loop until ptr is NULL.
            while !ptr.is_null() {
                let phonemes = (self.text_to_phonemes)(
                    &mut ptr as *mut *const c_void,
                    ESPEAK_CHARS_UTF8,
                    PHONEMEMODE_IPA,
                );
                if phonemes.is_null() {
                    break;
                }
                let s = CStr::from_ptr(phonemes).to_string_lossy();
                if !out.is_empty() {
                    out.push(' ');
                }
                out.push_str(&s);
            }
        }
        Ok(out)
    }
}

impl Drop for EspeakNg {
    fn drop(&mut self) {
        // Skip espeak_Terminate — calling it can race with libloading's unload
        // and we're a short-lived bench tool. The OS reaps the process state.
    }
}
