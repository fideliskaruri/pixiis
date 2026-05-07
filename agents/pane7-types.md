# Pane 7 — types.rs + ts-rs codegen

**Branch:** `wave1/types`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane7-types/`
**Wave:** 1 (Phase 1C — depends on Pane 5)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Port `src/pixiis/core/types.py` to Rust as **`frontend/src-tauri/src/types.rs`**, with serde derives and `ts-rs` codegen so the same shapes are available in TypeScript. This is the contract every other Rust module + every frontend page references.

## Dependency

**Wait until `frontend/src-tauri/Cargo.toml` exists.** Pane 5 is creating it. Poll every 30 s in your worktree:

```bash
while [ ! -f frontend/src-tauri/Cargo.toml ]; do
  sleep 30
  echo "Waiting for Pane 5 to scaffold src-tauri/..."
done
```

While you wait, do useful prep:

1. Read `/mnt/d/code/python/pixiis/src/pixiis/core/types.py` end-to-end.
2. Draft the Rust struct equivalents in a scratch file (`scratch/types_draft.rs`) so when Pane 5 finishes, you just move it into place.

## Working directory

`/mnt/d/code/python/pixiis/.worktrees/pane7-types/`

Work happens in `frontend/src-tauri/src/types.rs` once it exists.

## Deliverables

### 1. `frontend/src-tauri/src/types.rs`

Port these from Python (`core/types.py`):

| Python | Rust |
|---|---|
| `class AppSource(Enum)` | `#[derive(Serialize, Deserialize, TS, Debug, Clone, Copy, PartialEq, Eq)]` enum |
| `@dataclass class AppEntry` | struct with `id: String`, `name: String`, `source: AppSource`, `launch_command: String`, `exe_path: Option<PathBuf>`, `icon_path: Option<PathBuf>`, `art_url: Option<String>`, `metadata: serde_json::Map<String, Value>`. Helper methods on `&self` for `is_game()`, `is_installed()`, `is_favorite()`, `playtime_minutes()`, `last_played()`, `playtime_display()`. |
| `class TranscriptionEvent` | struct with `text: String`, `is_final: bool`, `timestamp: f64` |
| `class ControllerEvent` | struct with `button: u32`, `state: ButtonState`, `timestamp: f64`. ButtonState enum: Pressed, Held, Released. |
| `class AxisEvent` | struct with `axis: u32`, `value: f32`, `timestamp: f64` |
| `class MacroAction` | struct with `action: ActionKind`, `target: String` (or whatever the contract is). |
| `class NavigationEvent` | struct with `direction: Direction`. Direction enum: Up, Down, Left, Right, Activate, Back. |

Plus the service DTOs:
- `RawgGameData` — id, name, description, rating, metacritic, genres, platforms, screenshots, playtime, background_image, released
- `TwitchStream` — user_name, title, viewer_count, thumbnail_url, stream_url
- `YouTubeTrailer` — url, title, thumbnail (or whatever current youtube.py exposes)

All structs derive `Serialize, Deserialize, TS, Debug, Clone`. Use `#[ts(export)]` so generated `.ts` files land in `frontend/src/api/types/`.

### 2. `frontend/src-tauri/Cargo.toml` updates

Add dev-dependency `ts-rs = { version = "10", features = ["serde-compat", "no-serde-warnings"] }` (or current latest). Make sure it's added to `[dependencies]` not just `[dev-dependencies]` because `#[derive(TS)]` needs it.

### 3. `frontend/src-tauri/build.rs`

Wire ts-rs to emit `.ts` files at build time. Confirm output goes to `frontend/src/api/types/` (so frontend can `import { AppEntry } from './api/types/AppEntry'`).

### 4. Re-export from `lib.rs`

Add `pub mod types;` to `frontend/src-tauri/src/lib.rs` so commands can use the types.

### 5. Replace `serde_json::Value` placeholders in command stubs

The command stubs Pane 5 wrote use `Value` placeholders. Once your types exist, update the stubs to use proper types — only the **signatures**, the bodies still `unimplemented!()`. Don't break Pane 5's compile.

## Acceptance criteria

- `cargo build` from `frontend/src-tauri/` passes.
- `frontend/src/api/types/AppEntry.ts` (and the others) exists and matches the Rust shape.
- `STATUS.md` updated when types are landed (this unblocks Panes 8, 9 if they're using types).

## Out of scope

- **Don't** implement business logic.
- **Don't** touch other panes' modules (controller, services, library, voice).

## Reporting

- Append to `agents/STATUS.md` at start (waiting), unblock (Pane 5 done), milestone (types committed), final.
- Commit to `wave1/types`.
