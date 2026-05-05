//! Tauri command surface, split per subsystem.
//!
//! Each subsystem owns its own file. Bodies are stubs (fixture data or
//! `Err(AppError::NotImplemented)`) where the subsystem isn't fully wired;
//! `controller` is fully implemented (Pane 8).

pub mod config;
pub mod controller;
pub mod library;
pub mod services;
pub mod voice;
