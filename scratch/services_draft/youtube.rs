//! YouTube Data API v3 — first official-trailer match for a game.
//!
//! Mirrors `src/pixiis/services/youtube.py`. In-memory cache keyed by
//! lowercased game name.

use std::collections::HashMap;
use std::sync::Mutex;

use reqwest::Client;
use serde::Deserialize;

use crate::error::{AppError, AppResult};
use crate::types::YouTubeTrailer;

const ENDPOINT: &str = "https://www.googleapis.com/youtube/v3/search";

pub struct YouTubeClient {
    http: Client,
    api_key: String,
    cache: Mutex<HashMap<String, Vec<YouTubeTrailer>>>,
}

impl YouTubeClient {
    pub fn new(http: Client, api_key: String) -> Self {
        Self {
            http,
            api_key,
            cache: Mutex::new(HashMap::new()),
        }
    }

    /// Search for trailers and return the *top* match. Ports
    /// `YouTubeClient.search_trailers` from Python (which returns up to 5)
    /// down to a single `Option<YouTubeTrailer>` per the brief's command
    /// shape — the cache still holds the full list of 5.
    pub async fn get_trailer(&self, game_name: &str) -> AppResult<Option<YouTubeTrailer>> {
        if self.api_key.is_empty() {
            return Ok(None);
        }
        let cache_key = game_name.trim().to_lowercase();

        if let Some(hit) = self.cache.lock().unwrap().get(&cache_key).cloned() {
            return Ok(hit.into_iter().next());
        }

        let endpoint = std::env::var("PIXIIS_YOUTUBE_ENDPOINT_OVERRIDE")
            .unwrap_or_else(|_| ENDPOINT.to_string());
        let query = format!("{game_name} official trailer");
        let resp = self
            .http
            .get(&endpoint)
            .query(&[
                ("part", "snippet"),
                ("q", query.as_str()),
                ("type", "video"),
                ("maxResults", "5"),
                ("key", self.api_key.as_str()),
            ])
            .send()
            .await
            .map_err(http_err)?;
        if !resp.status().is_success() {
            return Ok(None);
        }
        let body: SearchResponse = resp.json().await.map_err(http_err)?;
        let trailers: Vec<YouTubeTrailer> = body
            .items
            .into_iter()
            .filter_map(|item| {
                let video_id = item.id.video_id?;
                let snippet = item.snippet;
                let thumb = snippet
                    .thumbnails
                    .high
                    .or(snippet.thumbnails.medium)
                    .or(snippet.thumbnails.default)
                    .map(|t| t.url)
                    .unwrap_or_default();
                Some(YouTubeTrailer {
                    video_id,
                    title: snippet.title,
                    thumbnail_url: thumb,
                    channel: snippet.channel_title,
                })
            })
            .collect();

        self.cache.lock().unwrap().insert(cache_key, trailers.clone());
        Ok(trailers.into_iter().next())
    }
}

fn http_err(e: reqwest::Error) -> AppError {
    AppError::Other(format!("youtube http: {e}"))
}

#[derive(Deserialize)]
struct SearchResponse {
    #[serde(default)]
    items: Vec<SearchItem>,
}

#[derive(Deserialize)]
struct SearchItem {
    #[serde(default)]
    id: VideoId,
    snippet: Snippet,
}

#[derive(Deserialize, Default)]
struct VideoId {
    #[serde(rename = "videoId")]
    #[serde(default)]
    video_id: Option<String>,
}

#[derive(Deserialize)]
struct Snippet {
    #[serde(default)]
    title: String,
    #[serde(rename = "channelTitle", default)]
    channel_title: String,
    #[serde(default)]
    thumbnails: Thumbnails,
}

#[derive(Deserialize, Default)]
struct Thumbnails {
    #[serde(default)]
    default: Option<Thumb>,
    #[serde(default)]
    medium: Option<Thumb>,
    #[serde(default)]
    high: Option<Thumb>,
}

#[derive(Deserialize)]
struct Thumb {
    url: String,
}

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;
    use serde_json::json;

    #[tokio::test]
    async fn returns_top_trailer() {
        let server = MockServer::start_async().await;
        server.mock(|when, then| {
            when.method(GET).path("/").query_param("key", "K");
            then.status(200).json_body(json!({
                "items": [{
                    "id": {"videoId": "abc123"},
                    "snippet": {
                        "title": "Hades — Official Launch Trailer",
                        "channelTitle": "Supergiant Games",
                        "thumbnails": {
                            "high": {"url": "https://yt.example/hi.jpg"},
                            "medium": {"url": "https://yt.example/md.jpg"}
                        }
                    }
                }]
            }));
        });
        std::env::set_var("PIXIIS_YOUTUBE_ENDPOINT_OVERRIDE", server.url("/"));
        let client = YouTubeClient::new(Client::new(), "K".into());
        let trailer = client.get_trailer("Hades").await.unwrap().expect("some");
        std::env::remove_var("PIXIIS_YOUTUBE_ENDPOINT_OVERRIDE");
        assert_eq!(trailer.video_id, "abc123");
        assert_eq!(trailer.thumbnail_url, "https://yt.example/hi.jpg");
        assert_eq!(trailer.channel, "Supergiant Games");
    }

    #[tokio::test]
    async fn none_when_no_api_key() {
        let client = YouTubeClient::new(Client::new(), String::new());
        assert!(client.get_trailer("Hades").await.unwrap().is_none());
    }
}
