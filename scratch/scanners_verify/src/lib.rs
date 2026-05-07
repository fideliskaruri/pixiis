//! Verifier crate (Wave 2, scanners-misc).
//!
//! Mounts the four scanner files from `src-tauri/src/library/` into a
//! tiny shim that supplies the only two upstream symbols they need
//! (`super::Provider` and `crate::types::{AppEntry, AppSource}`). Lets
//! us run `cargo test` on Linux while the full Tauri crate still needs
//! `pkg-config + libwebkit2gtk-4.1-dev` to build.

pub mod types {
    use serde::{Deserialize, Serialize};
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
        pub metadata: serde_json::Map<String, serde_json::Value>,
    }
}

pub mod library {
    pub trait Provider: Send + Sync {
        fn name(&self) -> &'static str;
        fn is_available(&self) -> bool;
        fn scan(&self) -> Vec<crate::types::AppEntry>;
    }

    #[path = "../../../../src-tauri/src/library/epic.rs"]
    pub mod epic;
    #[path = "../../../../src-tauri/src/library/gog.rs"]
    pub mod gog;
    #[path = "../../../../src-tauri/src/library/ea.rs"]
    pub mod ea;
    #[path = "../../../../src-tauri/src/library/startmenu.rs"]
    pub mod startmenu;
}
