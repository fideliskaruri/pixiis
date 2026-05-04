mod commands;
mod error;
pub mod services;
pub mod types;

pub use error::{AppError, AppResult};

use std::sync::Arc;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager,
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Single instance: focus the existing window if a second copy launches.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        // Autostart is scaffolded but disabled by default — toggled via app_set_autostart.
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Services container: shared HTTP client + caches for RAWG /
            // Twitch / YouTube / image loader. Pane 9 owns this; the real
            // config plumbing arrives with the config module — for now we
            // read the env vars `PIXIIS_RAWG_API_KEY`, `PIXIIS_YT_API_KEY`,
            // `PIXIIS_TWITCH_CLIENT_ID`, etc., as a stand-in.
            let services_cfg = services::ServicesConfig::from_lookup(|key| match key {
                "services.rawg.api_key" => std::env::var("PIXIIS_RAWG_API_KEY").ok(),
                "services.youtube.api_key" => std::env::var("PIXIIS_YT_API_KEY").ok(),
                "services.twitch.client_id" => std::env::var("PIXIIS_TWITCH_CLIENT_ID").ok(),
                "services.twitch.client_secret" => std::env::var("PIXIIS_TWITCH_CLIENT_SECRET").ok(),
                "services.twitch.access_token" => std::env::var("PIXIIS_TWITCH_TOKEN").ok(),
                _ => None,
            });
            let cache_dir = app
                .path()
                .app_cache_dir()
                .map(|p| p.join("images"))
                .unwrap_or_else(|_| std::env::temp_dir().join("pixiis-images"));
            let services = services::ServicesContainer::new(services_cfg, cache_dir)?;
            app.manage(Arc::new(services));

            // System tray with Open / Scan / Quit.
            let open_i = MenuItem::with_id(app, "open", "Open Pixiis", true, None::<&str>)?;
            let scan_i = MenuItem::with_id(app, "scan", "Scan Library", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_i, &scan_i, &quit_i])?;

            let mut tray_builder = TrayIconBuilder::with_id("pixiis-tray")
                .menu(&menu)
                .menu_on_left_click(false);
            if let Some(icon) = app.default_window_icon().cloned() {
                tray_builder = tray_builder.icon(icon);
            }
            let _tray = tray_builder
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.unminimize();
                            let _ = w.set_focus();
                        }
                    }
                    "scan" => {
                        // Frontend listens for this event and calls library_scan.
                        let _ = app.emit("tray://scan", ());
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // library
            commands::library::library_get_all,
            commands::library::library_scan,
            commands::library::library_launch,
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
            commands::voice::voice_speak,
            commands::voice::voice_inject_text,
            commands::voice::voice_get_transcript_log,
            // controller
            commands::controller::controller_register_macro,
            commands::controller::controller_get_state,
            commands::controller::vibration_pulse,
            // services
            commands::services::services_twitch_streams,
            commands::services::services_youtube_trailer,
            commands::services::services_oauth_start,
            commands::services::services_image_url,
            // config + app
            commands::config::config_get,
            commands::config::config_set,
            commands::config::config_reset,
            commands::config::app_quit,
            commands::config::app_show,
            commands::config::app_set_autostart,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
