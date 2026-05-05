//! RAWG.io API client — game metadata, ratings, screenshots.
//!
//! Mirrors `src/pixiis/services/rawg.py`. In-memory cache keyed by lowercased
//! search string and by `__id_<n>` for detail lookups.

use std::collections::HashMap;
use std::sync::Mutex;

use reqwest::Client;
use serde::Deserialize;
use serde_json::Value;

use crate::error::{AppError, AppResult};
use crate::types::RawgGameData;

const BASE_URL: &str = "https://api.rawg.io/api";

pub struct RawgClient {
    http: Client,
    api_key: String,
    cache: Mutex<HashMap<String, RawgGameData>>,
}

impl RawgClient {
    pub fn new(http: Client, api_key: String) -> Self {
        Self {
            http,
            api_key,
            cache: Mutex::new(HashMap::new()),
        }
    }

    /// Override the base URL — only used by tests with `httpmock`.
    #[cfg(test)]
    pub fn new_with_base(http: Client, api_key: String, _base: &str) -> Self {
        // Test path: cargo build sees the same constructor; tests reach the
        // mock via the `RAWG_BASE_URL_OVERRIDE` env var below.
        Self::new(http, api_key)
    }

    pub fn search_game(&self, name: &str) -> impl std::future::Future<Output = AppResult<RawgGameData>> + Send + '_ {
        let cache_key = name.trim().to_lowercase();
        let name_owned = name.to_string();
        async move {
            if self.api_key.is_empty() {
                return Ok(RawgGameData::default());
            }
            if let Some(hit) = self.cache.lock().unwrap().get(&cache_key).cloned() {
                return Ok(hit);
            }

            let base = base_url();
            let url = format!("{base}/games");
            let resp = self
                .http
                .get(&url)
                .query(&[
                    ("search", name_owned.as_str()),
                    ("key", self.api_key.as_str()),
                    ("page_size", "1"),
                ])
                .send()
                .await
                .map_err(reqwest_err)?;

            if !resp.status().is_success() {
                return Ok(RawgGameData::default());
            }
            let body: SearchResponse = resp.json().await.map_err(reqwest_err)?;
            let game = body
                .results
                .into_iter()
                .next()
                .map(parse_game)
                .unwrap_or_default();

            self.cache.lock().unwrap().insert(cache_key, game.clone());
            Ok(game)
        }
    }

    pub fn get_game_details(&self, id: u64) -> impl std::future::Future<Output = AppResult<RawgGameData>> + Send + '_ {
        let cache_key = format!("__id_{id}");
        async move {
            if self.api_key.is_empty() {
                return Ok(RawgGameData::default());
            }
            if let Some(hit) = self.cache.lock().unwrap().get(&cache_key).cloned() {
                return Ok(hit);
            }

            let base = base_url();
            let url = format!("{base}/games/{id}");
            let resp = self
                .http
                .get(&url)
                .query(&[("key", self.api_key.as_str())])
                .send()
                .await
                .map_err(reqwest_err)?;

            if !resp.status().is_success() {
                return Ok(RawgGameData::default());
            }
            let raw: Value = resp.json().await.map_err(reqwest_err)?;
            let game = parse_game(raw);
            self.cache.lock().unwrap().insert(cache_key, game.clone());
            Ok(game)
        }
    }
}

/// Test hook — `httpmock` sets `PIXIIS_RAWG_BASE_URL_OVERRIDE` so the client
/// hits the local mock server. Production code never sets this.
fn base_url() -> String {
    std::env::var("PIXIIS_RAWG_BASE_URL_OVERRIDE").unwrap_or_else(|_| BASE_URL.to_string())
}

fn reqwest_err(e: reqwest::Error) -> AppError {
    AppError::Other(format!("rawg http: {e}"))
}

#[derive(Deserialize)]
struct SearchResponse {
    #[serde(default)]
    results: Vec<Value>,
}

fn parse_game(obj: Value) -> RawgGameData {
    let get_str = |key: &str| obj.get(key).and_then(Value::as_str).unwrap_or("").to_string();
    let get_u64 = |key: &str| obj.get(key).and_then(Value::as_u64).unwrap_or(0);
    let get_f64 = |key: &str| obj.get(key).and_then(Value::as_f64).unwrap_or(0.0);

    let genres = obj
        .get("genres")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|g| g.get("name").and_then(Value::as_str).map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let platforms = obj
        .get("platforms")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|p| {
                    p.get("platform")
                        .and_then(|inner| inner.get("name"))
                        .and_then(Value::as_str)
                        .map(String::from)
                })
                .collect()
        })
        .unwrap_or_default();

    let screenshots = obj
        .get("short_screenshots")
        .and_then(Value::as_array)
        .map(|arr| {
            arr.iter()
                .filter_map(|s| s.get("image").and_then(Value::as_str).map(String::from))
                .collect()
        })
        .unwrap_or_default();

    let description = obj
        .get("description_raw")
        .and_then(Value::as_str)
        .map(String::from)
        .unwrap_or_else(|| get_str("description"));

    RawgGameData {
        id: get_u64("id"),
        name: get_str("name"),
        description,
        rating: get_f64("rating") as f32,
        metacritic: obj
            .get("metacritic")
            .and_then(Value::as_i64)
            .unwrap_or(0) as i32,
        genres,
        platforms,
        screenshots,
        playtime: get_u64("playtime") as u32,
        background_image: get_str("background_image"),
        released: get_str("released"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;
    use serde_json::json;

    #[tokio::test]
    async fn search_game_returns_first_result() {
        let server = MockServer::start_async().await;
        let _mock = server.mock(|when, then| {
            when.method(GET)
                .path("/games")
                .query_param("search", "Hades")
                .query_param("key", "TEST_KEY");
            then.status(200).json_body(json!({
                "results": [{
                    "id": 42,
                    "name": "Hades",
                    "description_raw": "Greek myth roguelike.",
                    "rating": 4.7,
                    "metacritic": 93,
                    "playtime": 25,
                    "background_image": "https://img.example/hades.jpg",
                    "released": "2020-09-17",
                    "genres": [{"name": "Action"}, {"name": "Indie"}],
                    "platforms": [{"platform": {"name": "PC"}}],
                    "short_screenshots": [{"image": "https://img.example/s1.jpg"}]
                }]
            }));
        });

        std::env::set_var("PIXIIS_RAWG_BASE_URL_OVERRIDE", server.base_url());
        let client = RawgClient::new(Client::new(), "TEST_KEY".to_string());
        let game = client.search_game("Hades").await.unwrap();
        std::env::remove_var("PIXIIS_RAWG_BASE_URL_OVERRIDE");

        assert_eq!(game.id, 42);
        assert_eq!(game.name, "Hades");
        assert_eq!(game.metacritic, 93);
        assert_eq!(game.genres, vec!["Action", "Indie"]);
        assert_eq!(game.platforms, vec!["PC"]);
        assert_eq!(game.screenshots, vec!["https://img.example/s1.jpg"]);
    }

    #[tokio::test]
    async fn search_game_returns_default_when_no_api_key() {
        let client = RawgClient::new(Client::new(), String::new());
        let game = client.search_game("Hades").await.unwrap();
        assert_eq!(game.id, 0);
        assert_eq!(game.name, "");
    }

    #[tokio::test]
    async fn search_game_uses_cache() {
        let server = MockServer::start_async().await;
        let mock = server.mock(|when, then| {
            when.method(GET).path("/games");
            then.status(200).json_body(json!({
                "results": [{"id": 1, "name": "Cached"}]
            }));
        });
        std::env::set_var("PIXIIS_RAWG_BASE_URL_OVERRIDE", server.base_url());
        let client = RawgClient::new(Client::new(), "K".to_string());
        let _ = client.search_game("Foo").await.unwrap();
        let _ = client.search_game("foo").await.unwrap(); // case-insensitive cache key
        std::env::remove_var("PIXIIS_RAWG_BASE_URL_OVERRIDE");
        mock.assert_hits(1);
    }
}
