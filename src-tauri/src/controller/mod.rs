//! Background controller subsystem (gilrs) for the always-on macro path.
//!
//! Foreground UI input still flows through the browser Gamepad API in the
//! frontend (`useController.ts`, `useSpatialNav.ts`); this module only fires
//! when the main window is hidden so the user can trigger voice / shortcuts
//! from the system tray.

pub mod backend;
pub mod macros;
pub mod mapping;

use std::sync::Arc;
use std::time::Duration;

use parking_lot::Mutex;
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

use self::backend::Backend;
use self::macros::{MacroDefRaw, MacroEngine, MacroParseError};
use self::mapping::{ButtonMapper, MapperConfig, MapperEvent};

/// What `controller_get_state` returns to the frontend.
#[derive(Serialize, Debug, Clone, Default)]
pub struct ControllerStateView {
    pub connected: bool,
    pub name: String,
}

#[derive(Default)]
struct ServiceState {
    connected: bool,
    name: String,
}

pub struct ControllerService {
    state: Mutex<ServiceState>,
    macros: Arc<MacroEngine>,
}

impl ControllerService {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            state: Mutex::new(ServiceState::default()),
            macros: Arc::new(MacroEngine::new()),
        })
    }

    pub fn macros(&self) -> Arc<MacroEngine> {
        self.macros.clone()
    }

    pub fn snapshot(&self) -> ControllerStateView {
        let s = self.state.lock();
        ControllerStateView {
            connected: s.connected,
            name: s.name.clone(),
        }
    }

    pub fn register_macro(&self, raw: MacroDefRaw) -> Result<(), MacroParseError> {
        self.macros.register(raw)
    }

    fn update_state(&self, connected: bool, name: Option<&str>) {
        let mut s = self.state.lock();
        s.connected = connected;
        s.name = name.map(str::to_string).unwrap_or_default();
    }

    /// Spawn the 60Hz polling loop on the Tauri async runtime. Runs until
    /// the app shuts down. If gilrs initialisation fails (no input
    /// subsystem on the host), logs once and returns without panicking.
    pub fn spawn(self: Arc<Self>, app: AppHandle, cfg: MapperConfig) {
        tauri::async_runtime::spawn(async move {
            let mut backend = match Backend::new() {
                Ok(b) => b,
                Err(e) => {
                    eprintln!("[controller] gilrs init failed: {e}; macros disabled");
                    return;
                }
            };
            let mut mapper = ButtonMapper::new(cfg);
            let mut ticker = tokio::time::interval(Duration::from_millis(16));
            ticker.set_missed_tick_behavior(
                tokio::time::MissedTickBehavior::Delay,
            );

            loop {
                ticker.tick().await;
                let raw = backend.poll();

                // Always reflect connection state, even when the frontend
                // owns input. controller_get_state needs this to stay fresh.
                self.update_state(backend.is_connected(), backend.active_name());

                let visible = window_visible(&app);
                if visible {
                    // Foreground: frontend hooks own input. Skip the macro
                    // path so we don't double-fire alongside the WebGamepad.
                    continue;
                }

                let events = mapper.tick(&raw);
                for ev in events {
                    let MapperEvent::Button(c) = ev else { continue };
                    for action in self.macros.match_event(&c) {
                        // Best-effort emit; a hidden window has no listeners
                        // but a tray-hosted webview will still see it on
                        // re-show via the Tauri event log.
                        let _ = app.emit("controller:macro", &action);

                        // Direct dispatch lives in later phases (voice
                        // start, send_keys, etc.). For now the emit above
                        // is the only side effect.
                    }
                }
            }
        });
    }
}

fn window_visible(app: &AppHandle) -> bool {
    match app.get_webview_window("main") {
        Some(w) => w.is_visible().unwrap_or(true),
        // No main window yet (during early startup) — treat as visible so
        // we don't fire macros before the UI exists.
        None => true,
    }
}
