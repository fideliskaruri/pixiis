# Pane 8 — gilrs controller backend

**Branch:** `wave1/controller`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane8-controller/`
**Wave:** 1 (Phase 4-prep — depends on Pane 5)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Sketch the Rust **controller subsystem** using the `gilrs` crate. This is the **background** controller path — the foreground UI continues to use the existing frontend Gamepad API hooks (`useController.ts`, `useSpatialNav.ts`). Your job is the always-on layer that fires macros when the window is hidden (e.g., voice trigger from system tray).

## Dependency

**Wait until `frontend/src-tauri/Cargo.toml` exists.** Same poll pattern as other dependent panes.

While waiting:

1. Read `/mnt/d/code/python/pixiis/src/pixiis/controller/{backend,mapping,macros}.py` end-to-end. Note the button/axis indices in `backend.py` — your indices must match.
2. Sketch the module shape in `scratch/controller_draft.md`.

## Working directory

`/mnt/d/code/python/pixiis/.worktrees/pane8-controller/`

Files land in `frontend/src-tauri/src/controller/` once it exists.

## Deliverables

### 1. `frontend/src-tauri/src/controller/mod.rs`

Module declarations + a public `ControllerService` struct that owns the polling task.

### 2. `frontend/src-tauri/src/controller/backend.rs`

- `gilrs = "0.10"` dependency added to `Cargo.toml`.
- A `Backend` struct wrapping `gilrs::Gilrs`.
- Public methods: `new()`, `poll()` (returns `Vec<Event>`), `connected_gamepads()`.
- Map gilrs events to the indices expected by `controller/mapping.py`:
  - South (A) = 0, East (B) = 1, West (X) = 2, North (Y) = 3
  - LB = 4, RB = 5, Select = 6, Start = 7
  - LS click = 8, RS click = 9
  - Axes: LS-X=0, LS-Y=1, RS-X=2, RS-Y=3, LT=4, RT=5, DPad-X=6, DPad-Y=7

### 3. `frontend/src-tauri/src/controller/mapping.rs`

Port `controller/mapping.py:ButtonMapper` — state machine that detects press / hold / release with `hold_threshold_ms` and emits typed events. Use Pane 7's `ControllerEvent` and `AxisEvent` types.

### 4. `frontend/src-tauri/src/controller/macros.rs`

Port `controller/macros.py:MacroEngine`. Read macros from config (`controller.macros` TOML section), match incoming events, emit `MacroAction` events.

Macros table format (already in `resources/default_config.toml:31-45`):
```toml
[controller.macros]
"button:0" = { mode = "press", action = "voice_record", target = "" }
"combo:4+5" = { mode = "combo", action = "send_keys", target = "alt+tab" }
```

### 5. Integration with the Tauri app

- A `ControllerService` that runs a background `tokio::spawn` polling loop at 60 Hz.
- When window is **hidden** (check via `tauri::WindowExt::is_visible`), emit Tauri events `controller:macro` to the JS frontend (which won't receive them since hidden — but the macro engine can also call commands directly: `voice_record` triggers `voice::pipeline::start_recording`).
- When window is **visible**, the background poller does **nothing for input** (frontend hooks own that). It still tracks connection state for `controller_get_state` command.

### 6. Update `lib.rs`

Register `ControllerService` in `tauri::Builder` setup; spawn the poller in `setup` callback.

### 7. Wire up command bodies (just these two)

- `controller_get_state` returns `{ connected: bool, name: String }` from your service.
- `controller_register_macro` updates the macro engine's table.

Other controller-related commands stay `unimplemented!()`.

## Acceptance criteria

- `cargo build` from `src-tauri/` succeeds.
- A unit test for `ButtonMapper` press/hold/release transitions.
- A unit test for `MacroEngine` matching `combo:4+5` against events.
- Manual test note in `STATUS.md`: "controller_get_state returns connected=true with my Xbox controller plugged in" (or false if not — the user can verify).

## Out of scope

- **Don't** touch frontend `useController.ts` or `useSpatialNav.ts` — they keep working as-is for foreground UI.
- **Don't** implement vibration here — Pane 9 owns `services::vibration`.
- **Don't** wire commands beyond the two listed.

## Reporting

- Update `agents/STATUS.md`.
- Commit to `wave1/controller`.
