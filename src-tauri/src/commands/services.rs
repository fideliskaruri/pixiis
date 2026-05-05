use std::sync::Arc;

use tauri::State;

use crate::error::{AppError, AppResult};
use crate::services::{image_loader::ImageLoader, oauth::OAuthFlow, twitch::TwitchClient, ServicesContainer};
use crate::types::{RawgGameData, TwitchStream, YouTubeTrailer};

#[tauri::command]
pub async fn services_twitch_streams(
    services: State<'_, Arc<ServicesContainer>>,
    game_name: String,
) -> AppResult<Vec<TwitchStream>> {
    if services.config.twitch_client_id.is_empty() {
        eprintln!("services_twitch_streams: no twitch client_id configured; returning empty");
        return Ok(Vec::new());
    }
    services.twitch.get_top_streams(&game_name).await
}

#[tauri::command]
pub async fn services_youtube_trailer(
    services: State<'_, Arc<ServicesContainer>>,
    game_name: String,
) -> AppResult<Option<YouTubeTrailer>> {
    services.youtube.get_trailer(&game_name).await
}

/// Look up RAWG metadata (description, screenshots, genres, etc.) by
/// game name. Returns `None` when no API key is configured or RAWG
/// returns no match — never bubbles a hard error to the UI.
#[tauri::command]
pub async fn services_rawg_lookup(
    services: State<'_, Arc<ServicesContainer>>,
    game_name: String,
) -> AppResult<Option<RawgGameData>> {
    if services.config.rawg_api_key.is_empty() {
        return Ok(None);
    }
    match services.rawg.search_game(&game_name).await {
        Ok(data) if data.id == 0 => Ok(None), // RAWG returned an empty/default
        Ok(data) => Ok(Some(data)),
        Err(e) => {
            eprintln!("services_rawg_lookup({game_name:?}) failed: {e}");
            Ok(None)
        }
    }
}

#[tauri::command]
pub async fn services_oauth_start(
    services: State<'_, Arc<ServicesContainer>>,
    provider: String,
) -> AppResult<String> {
    // Boot the local callback server, then build + return the auth URL the
    // frontend should open via tauri-plugin-shell. Phase 5 will park the
    // OAuthFlow in app state so a follow-up `services_oauth_wait` command
    // can drain the result; for now the flow is dropped after capturing the
    // port. The server self-terminates on callback, on `cancel()`, or via
    // OAuthFlow's internal watchdog.
    let flow = OAuthFlow::start().await?;
    let port = flow.port();
    drop(flow);

    let redirect = format!("http://127.0.0.1:{port}/callback");
    let auth_url = match provider.as_str() {
        "twitch" => {
            let client_id = services.config.twitch_client_id.clone();
            if client_id.is_empty() {
                return Err(AppError::InvalidArg(
                    "twitch client_id not configured".into(),
                ));
            }
            TwitchClient::authorize_url(&client_id, &redirect)
        }
        other => {
            return Err(AppError::InvalidArg(format!(
                "unknown oauth provider: {other}"
            )));
        }
    };
    Ok(auth_url)
}

#[tauri::command]
pub async fn services_image_url(
    services: State<'_, Arc<ServicesContainer>>,
    url: String,
) -> AppResult<String> {
    let path = services.images.request(&url).await?;
    Ok(ImageLoader::as_tauri_url(&path))
}
