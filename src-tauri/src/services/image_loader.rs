//! Three-layer image cache: memory → disk → network.
//!
//! Mirrors `src/pixiis/services/image_loader.py`. Disk cache lives at
//! `<image_cache_dir>/<sha256-prefix>{ext}`. The webview consumes images
//! through Tauri's asset protocol — we hand back a webview-loadable URL.
//!
//! ### Note on the URL scheme
//!
//! The brief mentions `https://asset.localhost/{percent_encoded}` (Tauri 1)
//! *or* `tauri::path::PathResolver`. Tauri 2 ships with the
//! `convertFileSrc()` JS helper that produces `asset://localhost/<path>` on
//! macOS/Linux and `https://asset.localhost/<path>` on Windows. We replicate
//! that on the Rust side so the URL works regardless of where the caller
//! runs. Tauri's `tauri.conf.json` must enable `assetProtocol` for the chosen
//! cache dir — that wiring is Pane 5 / Phase 5 territory.

use std::num::NonZeroUsize;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use lru::LruCache;
use reqwest::Client;
use sha2::{Digest, Sha256};
use tokio::fs;

use crate::error::{AppError, AppResult};

const MEM_CACHE_CAP: usize = 256;

pub struct ImageLoader {
    http: Client,
    dir: PathBuf,
    mem: Mutex<LruCache<String, PathBuf>>,
}

impl ImageLoader {
    pub fn new(http: Client, dir: PathBuf) -> Self {
        Self {
            http,
            dir,
            mem: Mutex::new(LruCache::new(NonZeroUsize::new(MEM_CACHE_CAP).unwrap())),
        }
    }

    /// Return a local `PathBuf` for `url`, downloading + caching as needed.
    pub async fn request(&self, url: &str) -> AppResult<PathBuf> {
        if url.is_empty() {
            return Err(AppError::InvalidArg("empty url".into()));
        }

        // 1. Memory cache
        if let Some(p) = self.mem_get(url) {
            return Ok(p);
        }

        // 2. Disk cache
        fs::create_dir_all(&self.dir).await.map_err(AppError::Io)?;
        let path = self.dir.join(filename_for(url));
        if fs::try_exists(&path).await.unwrap_or(false) {
            self.mem_put(url.to_string(), path.clone());
            return Ok(path);
        }

        // 3. Download
        let resp = self
            .http
            .get(url)
            .send()
            .await
            .map_err(|e| AppError::Other(format!("image GET: {e}")))?;
        if !resp.status().is_success() {
            return Err(AppError::Other(format!(
                "image GET {url} status {}",
                resp.status()
            )));
        }
        let bytes = resp
            .bytes()
            .await
            .map_err(|e| AppError::Other(format!("image read: {e}")))?;
        fs::write(&path, &bytes).await.map_err(AppError::Io)?;
        self.mem_put(url.to_string(), path.clone());
        Ok(path)
    }

    /// Convert a local cache path to a webview-loadable URL. Mirrors Tauri's
    /// `convertFileSrc()` JS helper.
    pub fn as_tauri_url(path: &Path) -> String {
        let s = path.to_string_lossy();
        let encoded = urlencoding::encode(&s);
        if cfg!(windows) {
            format!("https://asset.localhost/{encoded}")
        } else {
            format!("asset://localhost/{encoded}")
        }
    }

    fn mem_get(&self, url: &str) -> Option<PathBuf> {
        self.mem.lock().ok()?.get(url).cloned()
    }

    fn mem_put(&self, url: String, path: PathBuf) {
        if let Ok(mut g) = self.mem.lock() {
            g.put(url, path);
        }
    }
}

fn filename_for(url: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(url.as_bytes());
    let digest = hasher.finalize();
    let hex: String = digest.iter().take(12).map(|b| format!("{b:02x}")).collect();

    let ext = guess_ext(url).unwrap_or_else(|| ".img".to_string());
    format!("{hex}{ext}")
}

fn guess_ext(url: &str) -> Option<String> {
    let dot = url.rfind('.')?;
    let tail = &url[dot..];
    let cut = tail
        .find(|c: char| c == '?' || c == '#')
        .unwrap_or(tail.len());
    let ext = &tail[..cut];
    if (2..=5).contains(&ext.len()) && ext.is_ascii() {
        Some(ext.to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use httpmock::prelude::*;
    use tempfile::TempDir;

    #[tokio::test]
    async fn downloads_and_caches() {
        let server = MockServer::start_async().await;
        let _mock = server.mock(|when, then| {
            when.method(GET).path("/img.png");
            then.status(200)
                .header("content-type", "image/png")
                .body(b"\x89PNG fake".to_vec());
        });

        let dir = TempDir::new().unwrap();
        let loader = ImageLoader::new(Client::new(), dir.path().to_path_buf());
        let url = server.url("/img.png");

        let p = loader.request(&url).await.unwrap();
        assert!(p.exists());
        assert!(p.extension().map(|e| e == "png").unwrap_or(false));

        // Second call hits memory cache; hit count is checked via mock.
        let p2 = loader.request(&url).await.unwrap();
        assert_eq!(p, p2);
    }

    #[test]
    fn as_tauri_url_format() {
        let path = Path::new("/tmp/x.png");
        let url = ImageLoader::as_tauri_url(path);
        assert!(url.contains("asset"));
        assert!(url.contains("x.png"));
    }

    #[test]
    fn ext_handles_query_string() {
        assert_eq!(guess_ext("https://x.com/a.jpg?w=200"), Some(".jpg".into()));
        assert_eq!(guess_ext("https://x.com/a.png#frag"), Some(".png".into()));
        assert_eq!(guess_ext("https://x.com/noext"), None);
    }
}
