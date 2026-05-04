// Command modules. Bodies are stubs (fixture data or `Err(AppError::NotImplemented)`)
// — Pane 7 will lock down concrete types in `types.rs`, later phases land real logic.

pub mod config;
pub mod controller;
pub mod library;
pub mod services;
pub mod voice;
