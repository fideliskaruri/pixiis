//! Tauri command surface, split per subsystem.
//!
//! Each subsystem owns its own file. Pane 8 owns `controller`; the rest are
//! `unimplemented!()` stubs so the crate compiles end-to-end while later
//! phases (Pane 9 services / Phase 1B voice / Phase 2 library / Phase 4
//! config) fill in the bodies.

pub mod config;
pub mod controller;
pub mod library;
pub mod services;
pub mod voice;
