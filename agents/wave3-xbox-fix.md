# Wave 3 — Xbox / Game Pass detection broadening

## Symptom

Game Pass titles missing from the Home grid even when they appeared in
the user's Xbox app and the WinRT enumerator returned them. The Wave 1
spike (`spike/uwp-detect/RESULTS.md`) had already flagged this — its
final note said "Game Pass code path is wired but vacuous on this
machine (no `MicrosoftGame.Config` files installed)". The frontend
filter at `src/api/bridge.ts::enrich` keys off `metadata.is_xbox_game`,
which the scanner only flipped to `true` when a `MicrosoftGame.Config`
file existed in the package's install dir. Many Xbox PC titles ship
without one.

## Heuristics added

Replaces the single-signal `MicrosoftGame.Config` probe with a layered
OR. Any one positive signal flips `is_xbox_game = true`:

1. **`MicrosoftGame.Config` file exists** — original signal, kept as-is.
2. **Gaming capability declared in `AppxManifest.xml`** —
   `parse_manifest_full` now collects every `<Capability>`,
   `<rescap:Capability>`, `<DeviceCapability>`, and `<CustomCapability>`
   element across all namespaces. The match list (substring,
   case-insensitive on a lower-cased name) is:
   - `xbox` (catches `xboxLive`, `xboxAccessoryManagement`, …)
   - `gameBarServices`, `gameServices`, `gameMonitor`, `gameAccessory`,
     `gameChat`, `gamingDevice`, `broadcastServices`
3. **Package or family name matches a known game-publisher prefix**
   (case-insensitive). Conservative list — only entries we've seen
   shipping UWP titles. Includes:
   - `Microsoft.Xbox*`, `Microsoft.GamingApp`, `Microsoft.MinecraftUWP`
   - `Microsoft.MicrosoftSolitaireCollection`, `Microsoft.MicrosoftMahjong`,
     `Microsoft.MicrosoftSudoku`, `Microsoft.MicrosoftJackpot`,
     `Microsoft.MicrosoftTreasureHunt`, `Microsoft.MicrosoftBingo`,
     `Microsoft.MicrosoftUltimateWordGames`
   - `Microsoft.624F8B84B80` (Forza Horizon 5 publisher ID)
   - Studios: `Mojang*`, `MojangStudios*`, `KingDigitalEntertainment*`,
     `EAInc*`, `ElectronicArts*`, `TakeTwoInteractive*`, `2K*`,
     `2KGames*`, `BethesdaSoftworks*`, `BethesdaGameStudios*`,
     `Ubisoft*`, `UbisoftEntertainment*`, `SquareEnix*`, `Sega*`,
     `SEGAofAmericaInc*`, `BandaiNamco*`, `BandaiNamcoEntertainment*`,
     `Capcom*`, `Activision*`, `ActivisionPublishingInc*`, `Blizzard*`,
     `BlizzardEntertainment*`, `RiotGames*`, `ZeniMaxOnline*`,
     `InnerSloth*`, `ObsidianEntertainment*`, `FromSoftware*`
4. **Install dir contains a non-launcher `.exe`** — one-level read of
   the install dir (capped at 64 entries to stay cheap on packages
   with thousands of asset files). Excludes file-name fragments that
   indicate a launcher / updater / installer / redistributable:
   `gameLaunchHelper`, `launcher`, `launch`, `setup`, `install`,
   `update`, `updater`, `uninstall`, `vc_redist`, `vcredist`,
   `directx`, `dxsetup`, `crashreport`, `crashpad`, `easyAntiCheat`,
   `antiCheat`, `redistributable`, `helper`. If even one `.exe` whose
   stem doesn't contain those fragments exists, the heuristic fires.

## Skip-list extension

The broader heuristic catches several Microsoft-shipped UWP utilities
(Edge, Office, Teams, Photos, …) as "games" via the
non-launcher-exe path. To keep them out, the skip-list at
`src-tauri/src/library/xbox/skip_list.rs` was extended by **40 new
prefixes**:

`Microsoft.MicrosoftEdge`, `Microsoft.Edge`, `MicrosoftEdge.`,
`Microsoft.Office.`, `Microsoft.Office`, `Microsoft.OneDrive`,
`Microsoft.OneNote`, `Microsoft.Outlook`, `Microsoft.Teams`,
`MSTeams`, `MicrosoftTeams`, `Microsoft.Skype`, `Microsoft.MSPaint`,
`Microsoft.Paint`, `Microsoft.WindowsTerminal`, `Microsoft.PowerShell`,
`Microsoft.WindowsCalculator`, `Microsoft.WindowsAlarms`,
`Microsoft.WindowsCamera`, `Microsoft.WindowsFeedbackHub`,
`Microsoft.WindowsMaps`, `Microsoft.WindowsNotepad`,
`Microsoft.WindowsSoundRecorder`, `Microsoft.WindowsStore`,
`Microsoft.StorePurchase`, `Microsoft.Photos`,
`Microsoft.MicrosoftStickyNotes`, `Microsoft.MicrosoftOfficeHub`,
`Microsoft.GetHelp`, `Microsoft.Getstarted`, `Microsoft.People`,
`Microsoft.MixedReality`, `Microsoft.YourPhone`,
`Microsoft.WidgetsPlatformRuntime`, `Microsoft.ZuneMusic`,
`Microsoft.ZuneVideo`, `Microsoft.MoCamera`, `Microsoft.PowerAutomate`,
`Microsoft.Whiteboard`, `Microsoft.Todos`, `Microsoft.ScreenSketch`,
`Microsoft.MicrosoftFamilySafetyClient`,
`Microsoft.LanguageExperiencePack`,
`Microsoft.WindowsCommunicationsApps`, `Microsoft.UI.`,
`Microsoft.Dev.`, `Microsoft.PowerToys`, `MicrosoftCorporationII.`,
`MicrosoftCorporationIII.`, `Microsoft.Win32`,
`Microsoft.RemoteDesktop`, `Microsoft.MicrosoftPCManager`,
`Microsoft.HostApps`, `Microsoft.VisualStudio`, `MSIX.`.

## Override flag

`library.xbox.treat_all_as_games` (boolean, default `false`) — when
`true`, every package that survives the framework / display-name /
skip-list filters is reported with `is_xbox_game = true` regardless of
the heuristic. Wired into `XboxProvider::scan` via
`ConfigLookup::get_str` and the new `parse_bool` helper (accepts
`true`, `1`, `yes`, `on` — any case, with whitespace).

Surfaced in the UI at **Settings → Library → Show all Xbox apps as
games** with the hint text:
"Treat all detected Xbox / UWP packages as games. Useful if some of
your Game Pass titles are missing."

## Expected false-positive rate

After the skip-list extension:

- **Microsoft-shipped utilities** — should be zero false positives;
  every utility package family I'm aware of is now in the skip-list
  (Edge / Office / Teams / Calculator / Photos / Notepad / PowerToys /
  Visual Studio / etc.).
- **Third-party UWP utilities** (e.g. a partner app from a non-game
  publisher with a real `.exe` on disk) — could mis-classify as a
  game. Empirically rare on a Game Pass user's machine, but possible.
  The user can mark them via a future per-entry override
  (`section C.1` in the brief — deferred), or accept that they show on
  Home as "games" and uncheck the override flag.
- **Frameworks / system extensions** (`Microsoft.UI.Xaml.*`,
  `Microsoft.VCLibs.*`, …) — already filtered by `is_framework` and
  the original skip-list. No regression.

## What's still rejected

- Framework packages (`pkg.is_framework == true`) — never surface.
- Skip-list matches — never surface.
- `ms-resource:DisplayName` placeholders — dropped (manifest
  resolver couldn't find a real string).
- Packages whose `AppxManifest.xml` doesn't parse or has zero
  `<Application>` elements — dropped.
- Packages that pass everything but resolve to `GameLaunchHelper.exe`
  with no `MicrosoftGame.Config` to redirect into — dropped at the
  per-application stage.
- Packages with no real exe AND no game config — dropped (unchanged
  from Wave 1).

## Files touched

- `src-tauri/src/library/xbox/manifest.rs` — added `ManifestSummary`,
  `parse_manifest_full`, and capability collection across the
  `<Capabilities>` block (any namespace).
- `src-tauri/src/library/xbox/mod.rs` — layered detection + four
  helper fns (`has_gaming_capability`, `matches_game_publisher`,
  `has_significant_exe`, `parse_bool`), `ScanOptions`, config-aware
  `XboxProvider::new(Arc<dyn ConfigLookup>)`, and seven new tests.
- `src-tauri/src/library/xbox/skip_list.rs` — 40 new prefixes.
- `src-tauri/src/library/mod.rs` — pass `config.clone()` into
  `XboxProvider::new`.
- `src/pages/SettingsPage.tsx` — `xbox_treat_all_as_games` field on
  `SettingsState`, `library.xbox.treat_all_as_games` round-trip
  through `fromConfig` / `toPatch`, and the Library-section toggle.

## Verification

- Standalone Rust check (the workspace can't compile here without GTK
  system deps; copied the xbox module into `/tmp/xbox-check` against
  the same `quick-xml` / `serde_json` / `tempfile` versions): all 22
  unit tests pass.
- `npx tsc -b --noEmit` — clean.
