//! Verify shim — pulls in the real xbox.rs (and its sub-modules) via
//! #[path] so tests run against production code, not a copy. Stubs the
//! two crate seams the real module touches: `crate::types::{AppEntry,
//! AppSource}` (mirroring the exported wire shape) and `super::Provider`
//! (declared at the top of `library/mod.rs`).
//!
//! The on-disk shape is `src/library/mod.rs` so the `#[path]` inside
//! that file resolves through a directory that physically exists —
//! rustc opens the path as-is without canonicalising, so the parent
//! directories on the relative segment must be real.

pub mod types {
    use serde::{Deserialize, Serialize};
    use serde_json::{Map, Value};
    use std::path::PathBuf;

    #[derive(Serialize, Deserialize, Debug, Clone, Copy, PartialEq, Eq, Hash)]
    #[serde(rename_all = "lowercase")]
    pub enum AppSource {
        Steam,
        Xbox,
        Epic,
        Gog,
        Ea,
        Startmenu,
        Manual,
    }

    #[derive(Serialize, Deserialize, Debug, Clone)]
    pub struct AppEntry {
        pub id: String,
        pub name: String,
        pub source: AppSource,
        pub launch_command: String,
        pub exe_path: Option<PathBuf>,
        pub icon_path: Option<PathBuf>,
        pub art_url: Option<String>,
        pub metadata: Map<String, Value>,
    }
}

/// Mirrors the `Provider` trait declared in `library/mod.rs`.
pub trait Provider: Send + Sync {
    fn name(&self) -> &'static str;
    fn is_available(&self) -> bool;
    fn scan(&self) -> Vec<crate::types::AppEntry>;
}

pub mod library;

pub use library::xbox;
