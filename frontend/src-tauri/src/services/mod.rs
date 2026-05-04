//! HTTP-and-IO services: RAWG, Twitch, YouTube, OAuth callback, image cache,
//! controller vibration.
//!
//! Modules expose plain async Rust APIs. Tauri commands in `commands/services.rs`
//! wrap them as `#[tauri::command]`s. Pane 9 owns the modules; Phase 5 owns
//! the wiring between Tauri state and config.

pub mod image_loader;
pub mod oauth;
pub mod rawg;
pub mod twitch;
pub mod vibration;
pub mod youtube;

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use reqwest::Client;

use crate::error::{AppError, AppResult};

/// API keys + tokens pulled from `[services.*]` in `config.toml`.
#[derive(Clone, Debug, Default)]
pub struct ServicesConfig {
    pub rawg_api_key: String,
    pub youtube_api_key: String,
    pub twitch_client_id: String,
    pub twitch_client_secret: String,
    pub twitch_access_token: String,
}

impl ServicesConfig {
    /// Build from a config-like accessor. Phase 5 will plumb the real
    /// `Config` type; this signature accepts any `Fn(&str) -> Option<String>`.
    pub fn from_lookup<F>(get: F) -> Self
    where
        F: Fn(&str) -> Option<String>,
    {
        Self {
            rawg_api_key: get("services.rawg.api_key").unwrap_or_default(),
            youtube_api_key: get("services.youtube.api_key").unwrap_or_default(),
            twitch_client_id: get("services.twitch.client_id").unwrap_or_default(),
            twitch_client_secret: get("services.twitch.client_secret").unwrap_or_default(),
            twitch_access_token: get("services.twitch.access_token").unwrap_or_default(),
        }
    }
}

/// Owns shared HTTP + cache state for the entire services layer.
///
/// Stored in Tauri state as `tauri::State<Arc<ServicesContainer>>`.
pub struct ServicesContainer {
    pub config: ServicesConfig,
    pub http: Client,
    pub rawg: Arc<rawg::RawgClient>,
    pub youtube: Arc<youtube::YouTubeClient>,
    pub twitch: Arc<twitch::TwitchClient>,
    pub images: Arc<image_loader::ImageLoader>,
}

impl ServicesContainer {
    /// Construct with a config and an image-cache directory (typically
    /// `app_cache_dir()/images`).
    pub fn new(config: ServicesConfig, image_cache_dir: PathBuf) -> AppResult<Self> {
        let http = Client::builder()
            .timeout(Duration::from_secs(20))
            .user_agent(concat!("pixiis/", env!("CARGO_PKG_VERSION")))
            .build()
            .map_err(|e| AppError::Other(format!("reqwest build: {e}")))?;

        let rawg = Arc::new(rawg::RawgClient::new(http.clone(), config.rawg_api_key.clone()));
        let youtube = Arc::new(youtube::YouTubeClient::new(
            http.clone(),
            config.youtube_api_key.clone(),
        ));
        let twitch = Arc::new(twitch::TwitchClient::new(
            http.clone(),
            twitch::TwitchAuth {
                client_id: config.twitch_client_id.clone(),
                client_secret: config.twitch_client_secret.clone(),
                access_token: config.twitch_access_token.clone(),
            },
        ));
        let images = Arc::new(image_loader::ImageLoader::new(http.clone(), image_cache_dir));

        Ok(Self {
            config,
            http,
            rawg,
            youtube,
            twitch,
            images,
        })
    }
}
