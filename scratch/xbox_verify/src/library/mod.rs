//! Library shim — re-exports the verify crate's `Provider` trait under
//! the `super::` path the production xbox.rs expects, then loads
//! production xbox.rs directly via `#[path]`. The `xbox/` sub-modules
//! (`manifest.rs`, `skip_list.rs`) are picked up automatically by
//! rustc relative to xbox.rs's directory, so we don't have to mirror
//! the tree here.

pub use super::Provider;

#[path = "../../../../src-tauri/src/library/xbox/mod.rs"]
pub mod xbox;
