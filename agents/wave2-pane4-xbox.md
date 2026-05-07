# Wave 2 Pane 4 — Xbox / UWP scanner

**Branch:** `wave2/xbox`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-xbox/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Lift the **uwp-detect spike** into the production library at `src-tauri/src/library/xbox.rs`. The spike beat PowerShell on every metric (1.1 s vs 2.4 s, 34 extra AUMIDs found, 0 field mismatches).

## Reference

- Spike: `spike/uwp-detect/` (Wave 1, all targets passed)
- Spike results: `spike/uwp-detect/RESULTS.md`
- Python original: `src/pixiis/library/xbox.py` — note the skip-list (lines 81-103) for system packages
- Templates: `src-tauri/src/library/{steam,folder}.rs`

## Deliverables

1. **`src-tauri/src/library/xbox.rs`** — adapt the spike's main.rs into a `LibraryProvider` impl:
   - `name() -> "xbox"`
   - `is_available()` — returns true on Windows with `Management.Deployment` runtime accessible
   - `scan() -> Vec<AppEntry>` — runs the spike's enumeration, maps each UWP package to an AppEntry
   - `launch(app)` — invokes by AUMID via `windows::Win32::UI::Shell::IApplicationActivationManager` or `shell:appsFolder\<AUMID>`
   - `get_icon(app)` — returns the cached logo path from the manifest's `Square150x150Logo` field
2. **Skip-list:** port the system-package skip-list from `xbox.py:81-103` exactly. Add new entries the spike found that should be skipped (Microsoft.BioEnrollment, Microsoft.AAD.BrokerPlugin, etc — see the spike's RESULTS for the diff).
3. **Game Pass detection:** preserve the `is_xbox_game` metadata flag. The spike already wires the MicrosoftGame.Config probe — keep it.
4. **Cargo deps:** add to `Cargo.toml` (likely already partially there):
   - `windows = { ..., features = ["Management_Deployment", "ApplicationModel", "ApplicationModel_AppExtensions", "Foundation_Collections", "Storage"] }`
   - `quick-xml = "0.31"`
5. **Wire into `registry.rs::scan_all`** — add Xbox to the provider dispatch.
6. **Unit test:** mock the COM enumeration with a trait abstraction so the test can run without a real PackageManager. (The spike does this already — copy the pattern.)

## Acceptance criteria

- `cargo check` passes
- `scan()` returns ≥ same number of packages as the Python xbox.py on the same machine
- `launch()` opens the app for at least Forza Horizon and one Minecraft Launcher (manual smoke)
- Wall time ≤ 2 s for a typical install (per spike target)

## Out of scope

- Other storefronts — Pane 3
- Game Pass library refresh on subscription change (out of scope for v1)

## Reporting

Append to `agents/STATUS.md`. Commit to `wave2/xbox`.
