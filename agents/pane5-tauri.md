# Pane 5 — Tauri scaffold

**Branch:** `wave1/tauri-scaffold`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane5-tauri/`
**Wave:** 1 (Phase 1A — unblocks Panes 7, 8, 9)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Stand up the **`src-tauri/`** Rust crate inside `frontend/`, configure plugins, and create command stubs that return `unimplemented!()` (or canned fixture data) so the frontend can `invoke()` against them and HomePage continues to render with mock data.

You **unblock Panes 7, 8, 9** the moment `frontend/src-tauri/Cargo.toml` exists.

## Working directory

`/mnt/d/code/python/pixiis/.worktrees/pane5-tauri/frontend/`

## Reference

- `frontend/package.json` already has `@tauri-apps/api ^2.10.1`.
- `frontend/src/api/bridge.ts` currently calls Python sidecar via HTTP. **Don't replace it yet** — Phase 1A only stands up the Rust scaffold and command stubs.
- The full Tauri command surface is documented in the migration plan (28 commands). For this brief, stub **all** of them — implementation is later phases.

## Deliverables

1. **`frontend/src-tauri/`** initialized via `cargo tauri init` (or manual scaffolding if cargo-tauri-cli isn't installed). Choose:
   - App name: `Pixiis`
   - Window: 1280×800 frameless, transparent: false, drag region: top 52 px
   - Frontend dist path: `../dist`
   - Frontend dev URL: `http://localhost:5173`
2. **Plugins wired** in `Cargo.toml` and registered in `lib.rs`:
   - `tauri-plugin-single-instance`
   - `tauri-plugin-autostart`
   - `tauri-plugin-shell` (for opening URLs)
   - `tauri-plugin-fs` (limited scope)
   - `tauri-plugin-dialog` (for the File Manager page)
3. **`tauri.conf.json`**:
   - Window decorations off, frameless
   - Single-instance plugin enabled
   - Autostart plugin scaffolded but disabled by default
   - System tray with Open / Scan / Quit
4. **`capabilities/default.json`** with allow-list for the command surface.
5. **`src-tauri/src/main.rs`** — minimal, delegates to `lib.rs`.
6. **`src-tauri/src/lib.rs`** — runs `tauri::Builder`, registers plugins, registers all command stubs.
7. **`src-tauri/src/commands/`** subdirectory with stub modules:
   - `mod.rs`, `library.rs`, `voice.rs`, `controller.rs`, `services.rs`, `config.rs`
   - Each has `#[tauri::command]` functions matching the surface table below — bodies are `unimplemented!()` or return fixture data.
8. **`src-tauri/src/error.rs`** — a `thiserror` enum the commands return as `Result<T, AppError>`.
9. **Verify** with `cargo check -p pixiis` (or whatever the crate is named) — no compile errors.

## Command stub surface (28 commands)

```
library_get_all       library_scan          library_launch        library_toggle_favorite
library_search        library_get_icon      library_get_metadata
voice_start           voice_stop            voice_get_devices     voice_set_device
voice_speak           voice_inject_text     voice_get_transcript_log
controller_register_macro                   controller_get_state
config_get            config_set            config_reset
services_twitch_streams                     services_youtube_trailer
services_oauth_start                        services_image_url
playtime_get          vibration_pulse
app_quit              app_show              app_set_autostart
```

Use `serde_json::Value` placeholders for now — Pane 7 will replace them with proper types in `types.rs`.

## Acceptance criteria

- `cargo check` from `frontend/src-tauri/` passes.
- `frontend/src-tauri/Cargo.toml` exists (this is the signal Panes 7/8/9 are watching for).
- `npm run tauri dev` would boot a window (don't run — just verify config).
- Window is frameless, drag region top 52 px is wired.

## Out of scope

- **Don't** implement the actual command bodies. Stubs only.
- **Don't** touch React code.
- **Don't** delete `bridge.ts` — that's Phase 1A's last step but for now Home keeps working via HTTP.

## Reporting

- Update `agents/STATUS.md` the moment `Cargo.toml` exists (this releases the gate for Panes 7, 8, 9).
- Commit early and often. Suggested commits: scaffold → plugins → command stubs → cargo check passes.
