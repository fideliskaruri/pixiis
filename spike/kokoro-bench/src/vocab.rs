//! Phoneme→token vocab loader. Reads the same `kokoro_config.json` shipped with
//! `kokoro_onnx` (vendored alongside this crate as `src/kokoro_config.json`).

use anyhow::{Context, Result};
use serde::Deserialize;
use std::collections::HashMap;
use std::path::Path;

#[derive(Deserialize)]
struct Config {
    vocab: HashMap<String, i64>,
}

pub struct Vocab {
    /// Maps phoneme char → token id. Python stores keys as 1-codepoint strings.
    map: HashMap<char, i64>,
}

impl Vocab {
    pub fn embedded() -> Result<Self> {
        let raw = include_str!("kokoro_config.json");
        Self::from_json(raw)
    }

    pub fn from_path(p: &Path) -> Result<Self> {
        let raw = std::fs::read_to_string(p).with_context(|| format!("read vocab {}", p.display()))?;
        Self::from_json(&raw)
    }

    fn from_json(raw: &str) -> Result<Self> {
        let cfg: Config = serde_json::from_str(raw).context("parse kokoro_config.json")?;
        let mut map = HashMap::with_capacity(cfg.vocab.len());
        for (k, v) in cfg.vocab {
            let mut chars = k.chars();
            let first = chars.next().context("empty vocab key")?;
            if chars.next().is_some() {
                anyhow::bail!("vocab key {k:?} has more than 1 codepoint");
            }
            map.insert(first, v);
        }
        Ok(Self { map })
    }

    /// Tokenize a phoneme string. Mirrors Python:
    /// `[i for i in map(self.vocab.get, phonemes) if i is not None]`
    pub fn tokenize(&self, phonemes: &str) -> Vec<i64> {
        phonemes
            .chars()
            .filter_map(|c| self.map.get(&c).copied())
            .collect()
    }

    /// Filter a phoneme string to only chars present in vocab (matches the
    /// `phonemes = "".join(filter(lambda p: p in self.vocab, phonemes))` step).
    pub fn filter(&self, phonemes: &str) -> String {
        phonemes.chars().filter(|c| self.map.contains_key(c)).collect()
    }
}
