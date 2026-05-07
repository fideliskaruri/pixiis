# Pane 3 — UWP detection without PowerShell

**Branch:** `wave1/uwp-spike`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane3-uwp/`
**Wave:** 1 (Phase 0 — gate)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Replace the PowerShell child process at `src/pixiis/library/xbox.py:24-77` with direct **Windows Runtime COM** calls via the `windows` crate. PowerShell startup is 5–15 s and we can do better in <2 s with native COM.

## Working directory

Create the spike crate at:
`/mnt/d/code/python/pixiis/.worktrees/pane3-uwp/spike/uwp-detect/`

## Reference

The current Python implementation runs this PowerShell snippet (from `xbox.py:24-77`):
```powershell
Get-AppxPackage | Where-Object {...} | ForEach-Object {
    Get-AppxPackageManifest $_ | ...
    # extracts: Name, AUMID, Family, PackageName, Exe, Logo, InstallLocation, IsGame
}
```

It detects Xbox Game Pass titles by checking for `MicrosoftGame.Config` files in the install directory.

## Deliverables

1. Cargo binary crate `spike/uwp-detect/`:
   - `Cargo.toml`:
     ```toml
     [dependencies]
     windows = { version = "0.58", features = [
       "Management_Deployment",
       "ApplicationModel",
       "ApplicationModel_AppExtensions",
       "Foundation_Collections",
       "Storage",
     ] }
     quick-xml = "0.31"
     serde = { version = "1", features = ["derive"] }
     serde_json = "1"
     anyhow = "1"
     ```
   - `src/main.rs` that:
     - Initializes COM (`windows::Win32::System::Com::CoInitializeEx`).
     - Calls `PackageManager::FindPackagesByUserSecurityId(None)` to enumerate all installed packages for current user.
     - For each package, reads `Package::DisplayName()`, `Package::Id().Name()`, `Package::Id().FamilyName()`, `Package::InstalledLocation()`.
     - Parses `AppxManifest.xml` from the install location with `quick-xml` to extract:
       - `<Application Id=…>` → AUMID is `{family_name}!{app_id}`
       - `<Application Executable=…>` → exe path (relative to install dir)
       - `<VisualElements Square150x150Logo=…>` → logo path
     - Detects Xbox Game Pass: presence of `MicrosoftGame.Config` in install dir.
     - Filters out system packages (mirror the exclusion list at `xbox.py:81-103`).
     - Outputs JSON with the same shape as `xbox.py:64-72`:
       ```json
       [
         {
           "Name": "...", "AUMID": "...", "Family": "...",
           "PackageName": "...", "Exe": "...", "Logo": "...",
           "InstallLocation": "...", "IsGame": true
         }
       ]
       ```
2. `spike/uwp-detect/RESULTS.md` with:
   - List of detected packages
   - Wall-clock time
   - Diff against PowerShell output (run PowerShell once, save its output, compare)

## Acceptance criteria

| Metric | Target |
|---|---|
| Detected package count | ≥ same as PowerShell |
| Display names + AUMIDs + logos | stable, no missing fields |
| Wall time | ≤ 2 s |
| MicrosoftGame.Config detection | matches PowerShell on Game Pass titles |

## Kill criteria

If `MicrosoftGame.Config` parsing or AUMID assembly is impossible without spawning PowerShell, document and stop. Plan B: keep PowerShell sidecar **for UWP only** (acceptable — it runs once per scan).

## Dependencies

- Run on Windows. Spike pane needs to be on the user's Windows machine — this won't work in WSL alone.
- No other pane dependency.

## Out of scope

- Don't integrate with `src-tauri/`.
- Don't write the Xbox provider for the real port — that's Phase 2.

## Reporting

- Update `agents/STATUS.md`.
- Commit to `wave1/uwp-spike`.
- If COM/manifest parsing surprises you, ask the user — the chat is live in your tmux pane.
