# Controller Subsystem — Rust Sketch (Pane 8)

Notes captured while waiting for Pane 5's `frontend/src-tauri/Cargo.toml`. This is the **background, always-on** controller path. Foreground UI continues to use the Web Gamepad API via `useController.ts` / `useSpatialNav.ts`.

## Crates

```toml
gilrs = "0.10"
tokio = { features = ["sync", "time", "rt"] }
serde = "1"
toml  = "0.8"
parking_lot = "0.12"   # cheap Mutex<HashMap<...>> for macro table
```

`tauri`, `tokio` and `serde` come from Pane 5's `Cargo.toml`. We add `gilrs` and `parking_lot`.

## Shared types (Pane 7)

Pane 7 owns `ControllerEvent`, `AxisEvent`, `ButtonState`, `MacroMode`, `ActionKind`, `MacroAction` in `src-tauri/src/types.rs` (mirroring `src/pixiis/core/types.py`). We **import** them — we do not redefine them here.

**Confirmed shapes from `pane7-types/scratch/types_draft.rs`:**
- `ControllerEvent { button: u32, state: ButtonState, timestamp: f64, duration: f64 }`
- `AxisEvent { axis: u32, value: f32, timestamp: f64 }`
- `ButtonState::{Pressed, Held, Released}`
- `MacroMode::{Press, Hold, Combo}` (`#[serde(rename_all = "lowercase")]`)
- `ActionKind::{VoiceRecord, LaunchApp, SendKeys, NavigateUi, RunScript, Chain}` (`#[serde(rename_all = "snake_case")]` — matches the `voice_record` tokens used in default_config.toml)
- `MacroAction { action: ActionKind, mode: MacroMode, trigger: String, target: String, chain: Vec<MacroAction> }`

> Note: button index is **`u32`**, not `u8`. Update mapper internals accordingly.

## File layout

```
frontend/src-tauri/src/controller/
├── mod.rs        ControllerService, public façade
├── backend.rs    gilrs-backed Backend struct
├── mapping.rs    ButtonMapper state machine
└── macros.rs     MacroEngine
```

## `backend.rs` — gilrs index translation

gilrs ships `Button::*` and `Axis::*` enums; we translate to the same numeric indices Python's `InputsBackend` uses so existing config/macros remain valid.

| Index | gilrs Button   | Xbox label |
|------:|----------------|------------|
| 0     | South          | A          |
| 1     | East           | B          |
| 2     | West           | X          |
| 3     | North          | Y          |
| 4     | LeftTrigger    | LB         |
| 5     | RightTrigger   | RB         |
| 6     | Select         | Back/View  |
| 7     | Start          | Start/Menu |
| 8     | LeftThumb      | LS click   |
| 9     | RightThumb     | RS click   |

DPad will be exposed via gilrs as `DPadUp/Down/Left/Right` *or* via `Axis::DPadX/Y` depending on driver; we synthesize axes 6/7 from whichever fires.

| Index | gilrs Axis        | Notes                  |
|------:|-------------------|------------------------|
| 0     | LeftStickX        | -1..1                  |
| 1     | LeftStickY        | -1..1, **invert sign** to match XInput convention used by Python (down-positive) |
| 2     | RightStickX       | -1..1                  |
| 3     | RightStickY       | -1..1, **invert sign** |
| 4     | LeftZ             | LT, 0..1               |
| 5     | RightZ            | RT, 0..1               |
| 6     | DPadX (synth)     | -1, 0, 1               |
| 7     | DPadY (synth)     | -1, 0, 1               |

> NOTE: gilrs-0.10 normalizes axes already; just pass values through. The Y-invert is to match what `mapping.py` callers (e.g. spatial nav) expect downstream — confirm with Pane 7 once the Rust types land. If they ship `dpad_y_up_positive = true`, drop the invert.

```rust
pub struct Backend {
    gilrs: gilrs::Gilrs,
    /// Most-recently-active gamepad id; we track 1 controller for parity with Python.
    active: Option<gilrs::GamepadId>,
}

pub enum RawEvent {
    Button { index: u8, pressed: bool },
    Axis   { index: u8, value: f32  },
    Connected(String),
    Disconnected,
}

impl Backend {
    pub fn new() -> Result<Self, gilrs::Error>;
    pub fn poll(&mut self) -> Vec<RawEvent>;       // drains gilrs event queue
    pub fn connected_gamepads(&self) -> Vec<String>;
    pub fn active_name(&self) -> Option<String>;
}
```

`poll()` calls `gilrs.next_event()` in a loop until it returns `None`, translates each, updates `active` on Connected/Disconnected.

## `mapping.rs` — ButtonMapper

State machine ports `mapping.py:ButtonMapper`. `_ButtonTrack` becomes a `ButtonTrack` struct; the per-button list is `[ButtonTrack; 16]`.

```rust
pub struct ButtonMapper {
    tracks: [ButtonTrack; 16],
    recent_downs: Vec<(u8, Instant)>,
    hold_threshold: Duration,    // default 200ms from config
    combo_window: Duration,      // default 150ms
    deadzone: f32,               // default 0.15
    // axis state cache for deadzone gating
    axis_values: [f32; 8],
}

#[derive(Default)]
struct ButtonTrack {
    down: bool,
    down_since: Option<Instant>,
    held_fired: bool,
}

impl ButtonMapper {
    pub fn new(cfg: &Config) -> Self;
    pub fn ingest(&mut self, raw: &[RawEvent]) -> Vec<MapperEvent>;
}

pub enum MapperEvent {
    Button(ControllerEvent),  // PRESSED / HELD / RELEASED
    Combo(ControllerEvent),   // synthetic id = min*100 + max, state=PRESSED
    Axis(AxisEvent),
}
```

**Critical parity rule**: combo synthetic id is `min_btn * 100 + max_btn` (not `* 16` or shift); macros.py inspects this by recomputing the same id, so macros.rs must do the same. Verified in `mapping.py:147` and `macros.py:99-101`.

**Combo edge**: after a combo fires, `recent_downs` is cleared to prevent re-trigger while both buttons are still held. Port that exactly.

## `macros.rs` — MacroEngine

```rust
pub struct MacroEngine {
    macros: parking_lot::RwLock<Vec<MacroDef>>,
}

struct MacroDef {
    trigger: String,         // "button:0" / "combo:4+5"
    kind: TriggerKind,       // Button(u8) | Combo(u8, u8)
    mode: MacroMode,
    action: ActionType,
    target: String,
}

impl MacroEngine {
    pub fn new() -> Self;
    pub fn load_from_toml(&self, table: &toml::Table);
    pub fn register(&self, trigger: &str, def: MacroDefRaw) -> Result<()>;
    pub fn match_event(&self, ev: &ControllerEvent) -> Option<MacroAction>;
}
```

Trigger parser ports `_parse_trigger`:
- `button:N` → `TriggerKind::Button(N)`
- `combo:A+B` → `TriggerKind::Combo(min, max)`

Match rules (port of `MacroEngine._matches`):
- `Button(n)` + mode=Press → matches `event.button == n && state == PRESSED`
- `Button(n)` + mode=Hold  → matches `event.button == n && state == HELD`
- `Combo(a,b)` → matches `event.button == a*100 + b && state == PRESSED`

`controller_register_macro` command writes through `register()`.

## `mod.rs` — ControllerService

```rust
pub struct ControllerService {
    state: Arc<RwLock<ServiceState>>,
}

struct ServiceState {
    connected: bool,
    name: String,
}

pub struct ControllerStateView {
    pub connected: bool,
    pub name: String,
}

impl ControllerService {
    pub fn new() -> Arc<Self>;
    pub fn spawn(self: Arc<Self>, app: tauri::AppHandle, macros: Arc<MacroEngine>);
    pub fn snapshot(&self) -> ControllerStateView;
    pub fn macros(&self) -> Arc<MacroEngine>;
}
```

### Polling loop pseudocode

```rust
async fn run(self, app: AppHandle, macros: Arc<MacroEngine>) {
    let mut backend  = Backend::new().expect("gilrs init");
    let mut mapper   = ButtonMapper::new(&load_config());
    let mut ticker   = tokio::time::interval(Duration::from_millis(16)); // ~60Hz

    loop {
        ticker.tick().await;
        let raw = backend.poll();
        // Always update connection state, even when window visible.
        if !raw.is_empty() {
            self.update_state(backend.active_name(), true);
        }

        let visible = match app.get_webview_window("main") {
            Some(w) => w.is_visible().unwrap_or(true),
            None    => false,
        };
        if visible {
            // Foreground: frontend hooks own input; we only track connection.
            continue;
        }

        let events = mapper.ingest(&raw);
        for ev in events {
            if let MapperEvent::Button(c) | MapperEvent::Combo(c) = &ev {
                if let Some(action) = macros.match_event(c) {
                    // Direct dispatch where we can:
                    match action.action {
                        ActionType::VoiceRecord => crate::voice::start_recording(&app).await?,
                        _ => { /* fall through */ }
                    }
                    // Always emit to JS too (no listeners when hidden, harmless).
                    let _ = app.emit("controller:macro", &action);
                }
            }
        }
    }
}
```

> Open question: `crate::voice::start_recording` belongs to a future Pane 1 voice module. If it doesn't land before we're ready to wire, we leave a `TODO: dispatch to voice service` and only do `emit`. Brief allows that — it says "the macro engine *can* also call commands directly", not must.

### Window-visibility check

Tauri 2: `window.is_visible() -> tauri::Result<bool>`. Use `app.get_webview_window("main")`.

## Commands

Two only:

```rust
#[tauri::command]
fn controller_get_state(svc: State<Arc<ControllerService>>) -> ControllerStateView {
    svc.snapshot()
}

#[tauri::command]
fn controller_register_macro(
    svc: State<Arc<ControllerService>>,
    trigger: String,
    mode: String,
    action: String,
    target: Option<String>,
) -> Result<(), String> {
    svc.macros().register(&trigger, MacroDefRaw { mode, action, target: target.unwrap_or_default() })
        .map_err(|e| e.to_string())
}
```

All other controller commands stay `unimplemented!()` per brief.

## lib.rs wiring

```rust
let svc = ControllerService::new();
let macros = svc.macros();
// initial macro load from default_config.toml controller.macros section
macros.load_from_toml(&cfg["controller"]["macros"]);

tauri::Builder::default()
    .manage(svc.clone())
    .setup(move |app| {
        let app_handle = app.handle().clone();
        let svc = svc.clone();
        let macros = macros.clone();
        tokio::spawn(async move { svc.spawn(app_handle, macros).await; });
        Ok(())
    })
    .invoke_handler(tauri::generate_handler![
        controller_get_state,
        controller_register_macro,
        // ... others remain unimplemented stubs
    ])
```

Exact shape depends on what Pane 5 provides — adapt to their `App` type and `setup` signature.

## Tests

### `mapping::tests::press_hold_release`
1. Synthesize `RawEvent::Button { index: 0, pressed: true }`.
2. `ingest` → emits nothing yet (we're still under hold threshold).
3. Sleep → 250 ms (or inject `Instant::now()` via a clock trait — easier: parameterize `now: Instant` to `ingest_at`).
4. `ingest` again with no new raw → emits `HELD`.
5. `ingest` with `pressed: false` after hold → emits `RELEASED` with `duration > hold_threshold`.

For determinism, refactor mapper internals to take an explicit `now: Instant` argument. Public API can keep `Instant::now()` default by providing two methods.

### `macros::tests::combo_4_plus_5`
1. Engine `register("combo:4+5", mode=Combo, action=SendKeys, target="alt+tab")`.
2. Feed `ControllerEvent { button: 4*100+5, state: PRESSED }`.
3. Expect `Some(MacroAction { action: SendKeys, target: "alt+tab", .. })`.

### `macros::tests::button_press_match`
1. Engine `register("button:0", mode=Press, action=VoiceRecord, target="")`.
2. Feed `ControllerEvent { button: 0, state: PRESSED }` → `Some(...)`.
3. Feed `ControllerEvent { button: 0, state: HELD }` → `None` (mode is press, not hold).

## Coordination with Pane 9 (vibration)

Pane 9's draft says: *"`gilrs` — shared with Pane 8. **Take `&Gilrs`, never construct one.**"* So `ControllerService` must expose access to its `Gilrs` instance for the vibration service.

Polling needs `&mut Gilrs` (for `next_event()`); FF effects in gilrs 0.10 also typically need `&mut`. Cleanest pattern: wrap in `Arc<tokio::sync::Mutex<Gilrs>>` and lend it to vibration via an accessor on `ControllerService`. Polling acquires the lock once per tick (16 ms) and releases promptly; vibration acquires briefly to set effects. Contention is negligible.

If `tokio::sync::Mutex` proves awkward for the sync polling loop, fall back to `parking_lot::Mutex` (gilrs ops are non-blocking).

## Open questions / coordination

1. **Voice direct-dispatch** — confirm with voice owner (Pane 1 → Phase 1B) whether `voice::start_recording(&app)` exists. If not at wire-time, drop direct dispatch and only `emit("controller:macro", ...)`. Brief explicitly says emit-when-hidden is OK.
2. **Config loader** — Pane 5 / 9 may own config loading. Fall back to local `toml::from_str` of `resources/default_config.toml` if no shared loader exists yet.
3. **Y-axis sign convention** — Pane 7's draft does not declare a convention. Default to gilrs's native (up-positive) for spatial nav; Web Gamepad API is down-positive but the foreground UI handles its own input, so this only matters for the background macro path. No combos in default config use stick axes, so this is low-risk.
4. **Trigger threshold for macros that include LT/RT** — Python's `voice_trigger = "rt"` lives outside the macro table. Out of scope for Pane 8; voice owner can subscribe to `AxisEvent` directly.
