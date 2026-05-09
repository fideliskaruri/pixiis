mod commands;
mod controller;
mod error;
pub mod library;
pub mod services;
pub mod types;
pub mod voice;

pub use error::{AppError, AppResult};

use std::sync::Arc;

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Listener, Manager,
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

use crate::commands::config::{
    parse_summon_shortcut, read_summon_shortcut_string, DEFAULT_SUMMON_SHORTCUT,
};
use crate::controller::mapping::MapperConfig;
use crate::controller::ControllerService;

/// Bring the main window to the foreground from any code path
/// (tray click, single-instance, global shortcut). Calls `show`,
/// `unminimize`, and `set_focus` — Windows needs all three to reliably
/// raise from the tray + focus mid-game.
fn raise_main_window<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let controller_service = ControllerService::new();
    // Best-effort: load macro definitions from the bundled default config.
    // Phase 4 will replace this with the merged config loader.
    if let Some(table) = load_default_macros() {
        controller_service.macros().load_from_toml(&table);
    }

    tauri::Builder::default()
        .manage(controller_service.clone())
        // Single instance: raise the existing window if a second copy launches.
        // Important: show + unminimize + set_focus all three — show alone won't
        // pull a minimised window forward over a running game.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            raise_main_window(app);
        }))
        // Autostart is scaffolded but disabled by default — toggled via app_set_autostart.
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        // Global summon hotkey: pressing it from anywhere — game, browser,
        // desktop — raises Pixiis. Default is Ctrl+Shift+Alt+P; the actual
        // shortcut comes from `daemon.summon_shortcut` and is registered in
        // setup() below.
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        raise_main_window(app);
                    }
                })
                .build(),
        )
        .setup(move |app| {
            // Spawn the always-on controller poller. Reads gilrs at ~60Hz,
            // updates connection state, and fires macros only when the
            // window is hidden (foreground UI uses the Web Gamepad API).
            controller_service
                .clone()
                .spawn(app.handle().clone(), MapperConfig::default());

            // Big Picture: apply `ui.fullscreen` on startup. Best-effort —
            // a missing or unreadable config falls through to the
            // window's tauri.conf.json value (currently `false`). The
            // user can still toggle via F11, navbar double-click, or the
            // Settings → About checkbox.
            if load_ui_fullscreen(app.handle()).unwrap_or(false) {
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.set_fullscreen(true);
                }
            }

            // Services container: shared HTTP client + caches for RAWG /
            // Twitch / YouTube / image loader. Keys come from the user's
            // persisted `config.toml` (written by SettingsPage via
            // `config_set`), with env-var overrides for dev so a build
            // without a saved Settings page can still hit the live APIs.
            // Without this lookup the Game Detail trailer + LIVE NOW
            // sections would always render empty even after the user
            // saved their YouTube / Twitch credentials.
            let app_handle_for_keys = app.handle().clone();
            let services_cfg = services::ServicesConfig::from_lookup(|key| {
                let env_key = match key {
                    "services.rawg.api_key" => "PIXIIS_RAWG_API_KEY",
                    "services.youtube.api_key" => "PIXIIS_YT_API_KEY",
                    "services.twitch.client_id" => "PIXIIS_TWITCH_CLIENT_ID",
                    "services.twitch.client_secret" => "PIXIIS_TWITCH_CLIENT_SECRET",
                    "services.twitch.access_token" => "PIXIIS_TWITCH_TOKEN",
                    _ => return None,
                };
                if let Ok(v) = std::env::var(env_key) {
                    if !v.trim().is_empty() {
                        return Some(v);
                    }
                }
                commands::config::lookup_config_string(&app_handle_for_keys, key)
            });
            let cache_dir = app
                .path()
                .app_cache_dir()
                .map(|p| p.join("images"))
                .unwrap_or_else(|_| std::env::temp_dir().join("pixiis-images"));
            let services = services::ServicesContainer::new(services_cfg, cache_dir)?;
            app.manage(Arc::new(services));

            // Library service — scans Steam + Xbox/UWP + folders, persists favorites.
            let app_data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| std::env::temp_dir().join("pixiis"));
            let library = Arc::new(library::LibraryService::new(
                Arc::new(library::EmptyConfig::default()),
                app_data_dir,
                Vec::new(),
            ));
            app.manage(library.clone());

            // Running-game tracker — polls sysinfo every 5 s, resolves
            // URL-style launches into actual game PIDs, accrues playtime
            // when a process exits, and exposes library_running /
            // library_stop. Shares the LibraryService's overlay so
            // playtime persists through the same JSON file.
            let tracker = Arc::new(library::process::ProcessTracker::new(
                library.cache_path().to_path_buf(),
                library.overlay_handle(),
            ));
            // Rehydrate against any pre-existing scan so a Pixiis restart
            // while a game is running re-attaches to the live PID.
            tracker.rehydrate(&library.list());
            app.manage(tracker.clone());
            library::process::spawn_watcher(app.handle().clone(), tracker.clone());

            // Re-rehydrate after the next library scan so a fresh
            // `library_scan` picks up running games we couldn't see at
            // boot (the persisted list was empty / first launch). We
            // intentionally don't unsubscribe — the listener lives for
            // the lifetime of the app, same as the tracker itself.
            let tracker_for_listener = tracker.clone();
            let library_for_listener = library.clone();
            let _entries_listener =
                app.handle().listen("library:entries:changed", move |_| {
                    tracker_for_listener.rehydrate(&library_for_listener.list());
                });

            // Voice STT subsystem (Pane 1 / Wave 2). Loads the bundled
            // Whisper model from `resources/models/whisper/ggml-base.en-q5_1.bin`,
            // copies it into `%APPDATA%/pixiis/models/whisper/` on first
            // run, and brings up the Silero VAD when the `silero-vad`
            // feature is on (otherwise EnergyVad fallback). If the model
            // can't be found we still register the commands but they all
            // return a clean error instead of panicking the app.
            // Tauri exposes the bundle's resource directory through
            // `app.path().resource_dir()`. We pass it into the model
            // resolver so the lookup works regardless of how NSIS lays
            // out the install (some Tauri 2 layouts flatten the tree).
            let resource_dir = app.path().resource_dir().ok();
            let voice_slot = match voice::model::ensure_default_whisper_model_with(
                resource_dir.clone(),
            ) {
                Some(model_path) => {
                    let silero_path =
                        voice::model::ensure_silero_model_with(resource_dir);
                    match voice::VoiceService::new(
                        app.handle().clone(),
                        model_path,
                        silero_path,
                    ) {
                        Ok(svc) => commands::voice::VoiceServiceSlot {
                            service: Some(svc),
                            init_error: None,
                        },
                        Err(e) => {
                            eprintln!("[voice] init failed: {e}");
                            commands::voice::VoiceServiceSlot {
                                service: None,
                                init_error: Some(e.to_string()),
                            }
                        }
                    }
                }
                None => {
                    let msg = format!(
                        "whisper model {} not found in user dir or bundle",
                        voice::model::DEFAULT_WHISPER_FILENAME
                    );
                    eprintln!("[voice] {msg}");
                    commands::voice::VoiceServiceSlot {
                        service: None,
                        init_error: Some(msg),
                    }
                }
            };
            app.manage(Arc::new(voice_slot));

            // System tray with Open / Scan / Quit.
            let open_i = MenuItem::with_id(app, "open", "Open Pixiis", true, None::<&str>)?;
            let scan_i = MenuItem::with_id(app, "scan", "Scan Library", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_i, &scan_i, &quit_i])?;

            let mut tray_builder = TrayIconBuilder::with_id("pixiis-tray")
                .tooltip("Pixiis")
                .menu(&menu)
                .show_menu_on_left_click(false);
            if let Some(icon) = app.default_window_icon().cloned() {
                tray_builder = tray_builder.icon(icon);
            }
            let _tray = tray_builder
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => raise_main_window(app),
                    "scan" => {
                        // Frontend listens for this event and calls library_scan.
                        let _ = app.emit("tray://scan", ());
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                // Single-click + double-click both raise the window. Windows
                // launchers often special-case double-click (Steam, Discord);
                // single-click is friendlier and we keep both so muscle memory
                // from either camp works.
                .on_tray_icon_event(|tray, event| match event {
                    TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    }
                    | TrayIconEvent::DoubleClick {
                        button: MouseButton::Left,
                        ..
                    } => {
                        raise_main_window(tray.app_handle());
                    }
                    _ => {}
                })
                .build(app)?;

            // Register the configured global summon hotkey. Reads
            // `daemon.summon_shortcut` from config.toml, falls back to the
            // default. Logs and continues on failure — a bad shortcut must
            // never block app boot.
            let shortcut_str = read_summon_shortcut_string(app.handle())
                .unwrap_or_else(|| DEFAULT_SUMMON_SHORTCUT.to_string());
            if !shortcut_str.is_empty() {
                match parse_summon_shortcut(&shortcut_str) {
                    Ok(sc) => {
                        if let Err(e) = app.global_shortcut().register(sc) {
                            eprintln!(
                                "[summon] failed to register {shortcut_str}: {e}"
                            );
                        }
                    }
                    Err(e) => {
                        eprintln!("[summon] invalid shortcut {shortcut_str}: {e}");
                    }
                }
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // library
            commands::library::library_get_all,
            commands::library::library_scan,
            commands::library::library_launch,
            commands::library::library_running,
            commands::library::library_stop,
            commands::library::library_toggle_favorite,
            commands::library::library_search,
            commands::library::library_get_icon,
            commands::library::library_get_metadata,
            commands::library::playtime_get,
            // voice
            commands::voice::voice_start,
            commands::voice::voice_stop,
            commands::voice::voice_get_devices,
            commands::voice::voice_set_device,
            commands::voice::voice_inject_text,
            commands::voice::voice_get_transcript_log,
            commands::voice::voice_status,
            commands::voice::voice_download_model,
            // controller
            commands::controller::controller_register_macro,
            commands::controller::controller_get_state,
            commands::controller::vibration_pulse,
            // services
            commands::services::services_twitch_streams,
            commands::services::services_youtube_trailer,
            commands::services::services_rawg_lookup,
            commands::services::services_oauth_start,
            commands::services::services_image_url,
            // config + app
            commands::config::config_get,
            commands::config::config_set,
            commands::config::config_reset,
            commands::config::app_quit,
            commands::config::app_show,
            commands::config::app_set_autostart,
            commands::config::app_get_onboarded,
            commands::config::app_set_onboarded,
            commands::config::app_set_summon_shortcut,
            commands::config::app_get_summon_shortcut,
            // system power
            commands::system::system_sleep,
            commands::system::system_lock,
            commands::system::system_restart,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Read the merged `ui.fullscreen` flag for startup. Reads the user
/// override at `%APPDATA%/pixiis/config.toml` first; falls back to the
/// bundled `resources/default_config.toml`. Returns `None` if neither
/// file is parseable so the caller can default to the
/// `tauri.conf.json` value rather than getting stuck on a misread.
fn load_ui_fullscreen(app: &tauri::AppHandle) -> Option<bool> {
    // 1. User config (preferred).
    if let Ok(dir) = app.path().app_data_dir() {
        let user = dir.join("config.toml");
        if let Ok(text) = std::fs::read_to_string(&user) {
            if let Ok(value) = text.parse::<toml::Value>() {
                if let Some(b) = value
                    .get("ui")
                    .and_then(|u| u.get("fullscreen"))
                    .and_then(|v| v.as_bool())
                {
                    return Some(b);
                }
            }
        }
    }

    // 2. Bundled default — same candidate sweep as load_default_macros.
    let candidates = [
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.join("resources/default_config.toml"))),
        Some(std::path::PathBuf::from("../resources/default_config.toml")),
        Some(std::path::PathBuf::from("resources/default_config.toml")),
    ];
    for path in candidates.into_iter().flatten() {
        if let Ok(text) = std::fs::read_to_string(&path) {
            if let Ok(value) = text.parse::<toml::Value>() {
                if let Some(b) = value
                    .get("ui")
                    .and_then(|u| u.get("fullscreen"))
                    .and_then(|v| v.as_bool())
                {
                    return Some(b);
                }
            }
        }
    }
    None
}

/// Load the `[controller.macros]` table from the bundled
/// `resources/default_config.toml`. Returns `None` if the file isn't on
/// disk (dev runs without the resource bundle), letting the engine start
/// empty rather than panicking.
fn load_default_macros() -> Option<toml::value::Table> {
    let candidates = [
        // Resource bundle path, populated by tauri-build at release time.
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|p| p.join("resources/default_config.toml"))),
        // Dev fallback: `cargo run` from src-tauri/ — file lives one up.
        Some(std::path::PathBuf::from(
            "../resources/default_config.toml",
        )),
        // Dev fallback: `cargo run --manifest-path src-tauri/Cargo.toml` from
        // the project root — file lives in CWD.
        Some(std::path::PathBuf::from(
            "resources/default_config.toml",
        )),
    ];
    for path in candidates.into_iter().flatten() {
        if let Ok(text) = std::fs::read_to_string(&path) {
            let parsed: toml::Value = match text.parse() {
                Ok(v) => v,
                Err(_) => continue,
            };
            return parsed
                .get("controller")
                .and_then(|c| c.get("macros"))
                .and_then(|m| m.as_table())
                .cloned();
        }
    }
    None
}
