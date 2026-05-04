//! Wire-format types for the Tauri <-> React boundary.
//!
//! NOTE: this file is a stopgap. Pane 7 (`wave1/types`) owns the full
//! `types.rs` (~17 structs, ts-rs derive). This crate currently needs only
//! three service DTOs to compile, so we define just those here. When Pane 7
//! merges, accept their version entirely.

use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug, Clone, Default)]
pub struct RawgGameData {
    #[serde(default)]
    pub id: u64,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub rating: f32,
    #[serde(default)]
    pub metacritic: i32,
    #[serde(default)]
    pub genres: Vec<String>,
    #[serde(default)]
    pub platforms: Vec<String>,
    #[serde(default)]
    pub screenshots: Vec<String>,
    #[serde(default)]
    pub playtime: u32,
    #[serde(default)]
    pub background_image: String,
    #[serde(default)]
    pub released: String,
}

#[derive(Serialize, Deserialize, Debug, Clone, Default)]
pub struct TwitchStream {
    #[serde(default)]
    pub user_name: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub viewer_count: u64,
    #[serde(default)]
    pub thumbnail_url: String,
    #[serde(default)]
    pub stream_url: String,
}

#[derive(Serialize, Deserialize, Debug, Clone, Default)]
pub struct YouTubeTrailer {
    #[serde(default)]
    pub video_id: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub thumbnail_url: String,
    #[serde(default)]
    pub channel: String,
}
