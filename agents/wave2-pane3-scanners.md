# Wave 2 Pane 3 — Misc storefront scanners (Epic / GOG / EA / StartMenu)

**Branch:** `wave2/scanners-misc`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-scanners-misc/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Port four storefront scanners from Python to Rust. The pattern is mechanical — Wave 1 already shipped `steam.rs` and `folder.rs` as templates.

## Reference

- Python originals: `src/pixiis/library/{epic,gog,ea,startmenu}.py`
- Templates: `src-tauri/src/library/{steam,folder}.rs`
- Registry orchestrator: `src-tauri/src/library/registry.rs` — you wire each new provider here
- Trait: `src-tauri/src/library/mod.rs::LibraryProvider`
- Type: `src-tauri/src/types.rs::AppEntry`

## Deliverables

1. **`src-tauri/src/library/epic.rs`** — port `epic.py`:
   - Read JSON manifests from `C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests/*.item`
   - Each manifest is JSON; parse with serde_json
   - Launch URL: `com.epicgames.launcher://apps/{app_name}?action=launch`
2. **`src-tauri/src/library/gog.rs`** — port `gog.py`:
   - Read GOG Galaxy registry / install manifests
   - Source: `gog.py` shows the exact registry path
3. **`src-tauri/src/library/ea.rs`** — port `ea.py`:
   - Read EA Desktop install manifests
4. **`src-tauri/src/library/startmenu.rs`** — port `startmenu.py`:
   - Glob `*.lnk` shortcuts from `C:/ProgramData/Microsoft/Windows/Start Menu/Programs` and `%APPDATA%/Microsoft/Windows/Start Menu/Programs`
   - Parse `.lnk` files with the `lnk` crate
   - Launch via `os.startfile` equivalent — use `tauri::api::shell::open` or direct `windows::Win32::UI::Shell::ShellExecuteW`
5. **Update `src-tauri/src/library/mod.rs`** — add `pub mod epic; pub mod gog; pub mod ea; pub mod startmenu;`
6. **Update `src-tauri/src/library/registry.rs::scan_all`** — add the four new providers to the dispatch table, gated by config (`library.providers` array).

## Acceptance criteria

- `cargo check` passes
- Each provider has a unit test that exercises a fixture file (place fixtures under `src-tauri/tests/fixtures/`)
- Each `LibraryProvider::is_available()` returns false on machines without that storefront — no errors thrown
- The 4 new providers respect the same dedup behavior as steam.rs (case-insensitive on Windows by normalized path)

## Out of scope

- Xbox — Pane 4 owns it
- Manual provider — already in tree
- Game launching beyond the URL/registry pattern (no need to spawn full processes for these — let the storefront handle it)

## Reporting

Append to `agents/STATUS.md`. Commit incrementally per provider (4 commits is fine).
