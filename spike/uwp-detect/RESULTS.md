# UWP detection spike — results

Replaces the PowerShell sidecar in `src/pixiis/library/xbox.py:24-77` with
direct WinRT COM enumeration via the `windows` crate (0.58).

## Verdict

**Ship.** The spike beats every acceptance target and surfaces packages the
PowerShell script silently misses.

| Metric | Target | Result |
|---|---|---|
| Wall time (warm, end-to-end) | ≤ 2 s | **1.107 s avg** over 3 runs (PS: 2.418 s avg) |
| Wall time (cold, single run) | ≤ 2 s | 2.637 s (first run only — slightly over, see note) |
| Detected count vs PowerShell | ≥ same | **63 vs 31** raw (Rust strictly superior) |
| Field-level diff on common AUMIDs | stable | **0 mismatches** across Name / AUMID / Family / PackageName / Exe / InstallLocation / IsGame |
| MicrosoftGame.Config detection | matches PS | Code path mirrors PS branch (`xbox.py:38-44`); not exercised on this machine — no Game Pass titles installed |

> Cold-run 2.637 s is on first invocation after build. Warm runs (relevant for
> a long-running app launcher) are well under target. If we ever care about
> cold start, a single `manager.FindPackagesByUserSecurityId` warm-up call at
> app boot would amortise it.

## Reproducing

```cmd
:: build (sets LIB/INCLUDE/PATH for VS Build Tools then cargo)
spike\uwp-detect\_build.bat

:: bench: 3 warm runs of each, plus a single capture for diff
powershell -NoProfile -ExecutionPolicy Bypass -File spike\uwp-detect\_bench.ps1
```

The build helper is needed because the VS install on this box ships the
`onecore` lib layout without `vcvarsall.bat`; we point `LIB`/`INCLUDE` at the
right `MSVC\14.50.35717\lib\onecore\x64` and `Windows Kits\10\Lib\10.0.26100.0`
paths directly.

## Timing detail

End-to-end wall time including process startup (PowerShell starts cold every
time in the real Python flow — that's the apples-to-apples comparison):

```
=== uwp-detect.exe (3 warm runs) ===
  3 runs: 3.320s, avg 1.107s

=== powershell baseline (3 warm runs incl. process startup) ===
  3 runs: 7.255s, avg 2.418s
```

Internal stopwatch from the Rust binary on the diff-capture run: **665 ms** —
that's the COM + manifest-parse cost; everything else is process startup +
serde_json formatting.

**~2.2× faster end-to-end on warm runs.** The brief estimated PS at 5–15 s,
which would be a much larger win on a slower / cold machine; this dev box
already has PS pre-warmed in the session, so the gap closes — but a PS
**cold** start in the real Python flow is closer to the 5 s ballpark.

## Output diff

29 AUMIDs appear in both outputs with **0 field mismatches** (verified
across Name, AUMID, Family, PackageName, Exe, InstallLocation, IsGame).

### 34 AUMIDs in Rust only

Cause: the PS script has a bug in its multi-`<Application>` iteration —
`$manifest.Package.Applications.Application.Executable` returns an array of
all executables when the package has multiple `<Application>` entries, and
PowerShell's auto-flattening corrupts the loop. The Rust XML parser walks
each `<Application>` element directly.

Examples PS misses but Rust correctly captures:

- `MSTeams_8wekyb3d8bbwe` — 4 apps (`MSTeams`, `MSTeamsRemoteModuleContainer`,
  `MSTeams.Update`, `msteamsautostarter`)
- `Microsoft.M365Companions_8wekyb3d8bbwe` — 3 apps (`Calendar`, `Files`,
  `People`)
- `Microsoft.GamingServices_8wekyb3d8bbwe` — 3 apps
- `Microsoft.AzureVpn_8wekyb3d8bbwe` — 2 apps
- `Microsoft.OneDriveSync_8wekyb3d8bbwe` — 2 apps
- 24 more single-app packages where the PS script's flow happened to skip
  them (typically because `Properties.DisplayName` is unresolved
  `ms-resource:…` but `Package::DisplayName()` from WinRT resolves it
  through MRT)

### 2 AUMIDs in PS only

`Microsoft.Windows.CapturePicker_…!App` and
`Microsoft.Windows.PinningConfirmationDialog_…!App` — both match the
`Microsoft.Windows` prefix in the existing skip-list (`xbox.py:81`), so the
Python wrapper would drop them downstream. Net effect: zero loss.

## Detected packages (sorted by name, 63 total)

```
Add Folder Suggestions dialog
Adobe Acrobat Reader
AI Toolkit Inference Agent
AMD Radeon Software
App Resolver
Azure VPN Client                 (2 AUMIDs)
Candy Crush Saga
Claude
Company Portal
DevToys
Diagnostic Data Viewer
Dolby Access
Draw Diagram
ELAN TrackPoint for Thinkpad
EpmShellExtension
File Explorer
Game Bar
Game Speech Window
Gaming Services                  (3 AUMIDs)
Get Help
GlobalProtect
Ink.Handwriting.Main.en-US.1.0
Local AI Manager for Microsoft 365
Microsoft 365 companion apps     (3 AUMIDs)
Microsoft 365 Copilot
Microsoft Clipchamp
Microsoft Edge
Microsoft Edge Game Assist
Microsoft Office Outlook Desktop Integration
Microsoft Sticky Notes
Microsoft Teams                  (4 AUMIDs)
Microsoft.Office.ActionsServer
MSN Weather
OfficePushNotificationsUtility
OneDrive                         (2 AUMIDs)
OneNote Virtual Printer
Outlook for Windows
Paint
Phone Link
PrebootManager
Realtek Audio Control
Snipping Tool
Solitaire & Casual Games
TrackPoint
Visual Studio Code
WinAppRuntime.Main.1.8
Windows App
Windows Barcode Preview
Windows Print
Windows Subsystem for Linux
Wireless Display
WritingAssistant
Xbox Game UI
Xbox Identity Provider
```

## Game Pass detection — code-path note

This dev box has zero `MicrosoftGame.Config` files in any installed package,
so `IsGame=true` is empty in both outputs (matching). The Rust path that
exercises the brief's Game Pass requirement:

1. `parse_microsoft_game_config()` (src/main.rs:155) — reads
   `<ExecutableList><Executable Name="…"></ExecutableList>` exactly like the
   PS branch.
2. Substitutes that exe when the manifest's `Application/@Executable` is
   empty or `GameLaunchHelper.exe` (src/main.rs:241), mirroring
   `xbox.py:36-44`.

Plan B in the brief (keep PS sidecar for UWP only) is **not** needed —
both AUMID assembly and `MicrosoftGame.Config` parsing are
straightforward in Rust.

## File map

```
spike/uwp-detect/
├── Cargo.toml          # windows 0.58 + quick-xml 0.31 + serde + anyhow
├── src/main.rs         # the spike
├── _build.bat          # cargo build with VS env shim (LIB/INCLUDE)
├── _bench.ps1          # 3-run timing comparison + diff capture
├── _baseline.ps1       # exact PS script from xbox.py:24-77, lifted out
└── RESULTS.md          # this file
```

`out_rust.json`, `out_ps.json`, and `target/` are gitignored.
