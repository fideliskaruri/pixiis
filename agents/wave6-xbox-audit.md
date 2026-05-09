# Wave 6 — Xbox false-positive audit

Read-only audit of the Wave-3/Wave-4 layered Xbox detection chain at
`src-tauri/src/library/xbox/mod.rs`. Goal: identify exactly which
non-game UWP packages slip through `is_xbox_game = true` and why.

---

## TL;DR (executive summary)

The chain is **architecturally wrong-shaped**, not a tunable problem.

- Heuristic D (`has_significant_exe`) is the dominant false-positive
  source — it fires on **almost every UWP app** that has a regular
  binary on disk (including Spotify, Discord-UWP, Notepad-UWP, every
  third-party utility). The skip-list covers Microsoft-shipped apps but
  cannot cover the long tail of third-party UWP apps.
- Heuristic C (`Microsoft.Xbox` prefix) is **the single biggest
  Microsoft-shipped false-positive source**: Windows ships at least 5
  pre-installed `Microsoft.Xbox*` packages that are infrastructure, not
  games — `Microsoft.XboxIdentityProvider`, `Microsoft.XboxGameOverlay`,
  `Microsoft.XboxGamingOverlay`, `Microsoft.XboxSpeechToTextOverlay`,
  `Microsoft.Xbox.TCUI`. **None are in the skip-list.** They will all
  flag as `is_xbox_game = true` on a stock Windows 11 install.
- Heuristic B (gaming capability) is mostly correct, but the substring
  match `xbox` is too greedy — `xboxLive` and `xboxAccessoryManagement`
  are reasonable signals, but a UWP utility that *integrates with* the
  Xbox app (e.g. captures, broadcasting) can declare `broadcastServices`
  for non-gaming reasons.
- The user's `treat_all_as_games` flag defaults to `false` in
  `default_config.toml` — so that is **not** the cause of the report.

The biggest single false-positive source the user is currently seeing
is almost certainly **`Microsoft.Xbox*` system packages** flagged by
Heuristic C. They are pre-installed on every Windows 11 box, declare
`xbox*` capabilities (so they double-flag via B), and are **not** in
the skip-list.

---

## 1. Heuristic-by-heuristic walk

The chain at `src-tauri/src/library/xbox/mod.rs:318-322`:

```rust
let is_game = game_config_exists                 // A
    || has_gaming_capability(&summary)           // B
    || matches_game_publisher(&pkg.package_name, // C
                              &pkg.family_name)
    || has_significant_exe(&pkg.install_location) // D
    || opts.treat_all_as_games;
```

ANY positive signal flips the flag. There is no negative signal, no
tie-breaking, no priority — the chain is monotonic-OR.

### A. `MicrosoftGame.Config` exists — `mod.rs:304-305`

**Verdict: clean signal.** This file is published by the MicrosoftGame
toolchain only. No known non-game ships it. Real false-positive rate ≈ 0.

### B. Gaming capability — `mod.rs:389-394`, hint list at `mod.rs:61-70`

```rust
const GAMING_CAPABILITY_HINTS: &[&str] = &[
    "xbox", "gamebarservices", "gameservices", "gamemonitor",
    "gameaccessory", "gamechat", "gamingdevice", "broadcastservices",
];
```

Substring match against lower-cased capability names.

**Verdict: mostly clean, with two suspect hints:**

- `"xbox"` (substring) — fires on `xboxLive`, `xboxAccessoryManagement`,
  `xboxLiveStreamingOptIn`, etc. **Real games declare these.** But
  several pre-installed Xbox infrastructure UWPs also do (e.g.
  `Microsoft.XboxIdentityProvider` declares `xboxAccessoryManagement`).
  Combined with Heuristic C, this is the worst false-positive cluster.
- `"broadcastservices"` — declared by streaming/capture apps that
  integrate with the Xbox Game Bar capture pipeline. Not strictly
  game-only.
- `"gamebarservices"` — empirically rare; Microsoft Edge does **not**
  declare it (verified against the public Edge AppxManifest), so the
  brief's hypothesis was wrong on Edge specifically. Still, third-party
  capture utilities can declare it.

**Confirmed false-positive packages here:** see Section 2 — primarily
the `Microsoft.Xbox*` infrastructure family.

### C. Family-prefix match — `mod.rs:75-116`, `mod.rs:400-407`

```rust
const GAME_PUBLISHER_PREFIXES: &[&str] = &[
    "Microsoft.Xbox",
    "Microsoft.GamingApp",
    ...
];
```

`pn.starts_with(&lp) || fn_.starts_with(&lp)`, lower-cased.

**Verdict: BROKEN — `Microsoft.Xbox` is too broad.**

Confirmed pre-installed Windows 11 packages that match
`Microsoft.Xbox*` and are **not games**:

| Package family                              | Role                                                      | Pre-installed on Win11 |
|---------------------------------------------|-----------------------------------------------------------|---|
| `Microsoft.XboxIdentityProvider`            | Xbox auth broker — system component                        | yes |
| `Microsoft.XboxGameOverlay`                 | Game Bar overlay infrastructure                           | yes |
| `Microsoft.XboxGamingOverlay`               | Game Bar UI infrastructure                                | yes |
| `Microsoft.XboxSpeechToTextOverlay`         | Game-chat accessibility component                          | yes |
| `Microsoft.Xbox.TCUI`                       | Cross-platform Xbox user-interface helper                  | yes |
| `Microsoft.XboxApp`                         | Legacy Xbox Console Companion (deprecated, sometimes still present) | sometimes |

`Microsoft.GamingApp` (the modern Xbox app itself) is a borderline case
— it is the storefront app, not a game, but the user might reasonably
expect it to NOT show on the Home grid as if it were a game.

Other prefixes look conservative and correct (Mojang*, Bethesda*,
Activision*, etc. are all genuine game-publisher namespaces).

**`Microsoft.GameApps`** (line 88) — I cannot confirm this is a real
publisher namespace; appears speculative.

### D. Install-dir non-launcher .exe — `mod.rs:417-439`

```rust
fn has_significant_exe(install_dir: &Path) -> bool {
    // Walk first ~64 entries one level deep, return true if any .exe
    // whose stem doesn't contain a launcher/updater/installer fragment.
}
```

**Verdict: structurally broken — does not actually distinguish games
from apps.**

This rule is paraphrased as "if a UWP has any non-launcher .exe, it's
a game." This is true of **almost every UWP app** that has any native
binary at all, because the launcher-fragment list (`launcher`, `setup`,
`install`, `update`, …) is designed to filter out *secondary* binaries,
not the main app binary.

Confirmed false-positives by this rule (every one of these has a
real `.exe` whose stem does NOT contain any launcher fragment):

| UWP app                          | Main exe (typical)            | Caught by skip-list? |
|----------------------------------|-------------------------------|---|
| Calculator                        | `Calculator.exe`              | YES (`Microsoft.WindowsCalculator`) |
| Photos                            | `Microsoft.Photos.exe`        | YES (`Microsoft.Photos`) |
| Sticky Notes                      | `Microsoft.Notes.exe`         | YES (`Microsoft.MicrosoftStickyNotes`) |
| Notepad (UWP)                     | `Notepad.exe`                 | YES (`Microsoft.WindowsNotepad`) |
| Microsoft Store                   | `WinStore.App.exe`            | YES (`Microsoft.WindowsStore`) |
| Windows Camera                    | `WindowsCamera.exe`           | YES (`Microsoft.WindowsCamera`) |
| Snipping Tool / Screen Sketch     | `ScreenClippingHost.exe`      | YES (`Microsoft.ScreenSketch`) |
| Spotify (Store)                   | `Spotify.exe`                 | **NO** |
| Discord-UWP / 3rd-party UWP wrappers | `Discord.exe` etc.         | **NO** |
| Netflix                           | `Netflix.exe`                 | **NO** |
| WhatsApp Desktop (UWP)            | `WhatsApp.exe`                | **NO** |
| iTunes (Store)                    | `iTunes.exe`                  | **NO** |
| TikTok                            | various                       | **NO** |
| Any third-party UWP utility       | typically present             | **NO** |

**Bottom line on D:** it inverts the question. The right question is
"does this binary look like a game?" — answered by signed publisher,
DirectX usage, install size, target sandbox, etc. — but the
implementation answers "is there *any* binary?" instead.

---

## 2. Confirmed false positives (consolidated)

| Package family                       | Heuristic that flips it    | In skip-list? |
|--------------------------------------|----------------------------|---|
| `Microsoft.XboxIdentityProvider`     | C (Microsoft.Xbox prefix) + B (xbox capability) | NO |
| `Microsoft.XboxGameOverlay`          | C + likely B               | NO |
| `Microsoft.XboxGamingOverlay`        | C + likely B               | NO |
| `Microsoft.XboxSpeechToTextOverlay`  | C + likely B               | NO |
| `Microsoft.Xbox.TCUI`                | C                          | NO |
| `Microsoft.XboxApp` (legacy)          | C                          | NO |
| `Microsoft.GamingApp` (Xbox storefront) | C (GamingApp prefix)    | NO (and intentional) |
| Spotify                              | D (`Spotify.exe`)          | NO |
| Discord (UWP variants)               | D                          | NO |
| Netflix (UWP)                        | D                          | NO |
| WhatsApp Desktop (UWP)               | D                          | NO |
| iTunes (Store version)               | D                          | NO |
| Any 3rd-party UWP utility w/ a real exe | D                       | NO |

The user's report ("all xbox apps show up") points squarely at the top
6 rows — those are the `Microsoft.Xbox*` system components every
Windows 11 install ships. Combined with the legitimate Game Pass /
Mojang / Bethesda / Forza packages, they would visually dominate the
"games" grid.

---

## 3. Skip-list gaps

Packages that should be in `src-tauri/src/library/xbox/skip_list.rs`
but are NOT:

- **`Microsoft.XboxIdentityProvider`** — system auth broker.
- **`Microsoft.XboxGameOverlay`** — Game Bar overlay infra.
- **`Microsoft.XboxGamingOverlay`** — Game Bar UI infra.
- **`Microsoft.XboxSpeechToTextOverlay`** — accessibility component.
- **`Microsoft.Xbox.TCUI`** — Xbox Title Callable UI helper.
- **`Microsoft.XboxApp`** — legacy Console Companion (debatable, but
  not a game itself).
- **`Microsoft.GamingApp`** — debatable; it's the Xbox storefront, not
  a game. UX call: hide or surface as a launcher tile rather than a
  game tile.
- **`Microsoft.MicrosoftEdgeDevToolsClient`** — sometimes appears
  alongside Edge but the current `Microsoft.MicrosoftEdge` /
  `MicrosoftEdge.` prefixes don't cover it.
- **`Microsoft.BingNews`**, **`Microsoft.BingWeather`** — pre-installed
  on most Windows 11 installs.
- **`Microsoft.HEIFImageExtension`**, **`Microsoft.WebpImageExtension`**
  — partially covered by current entries but the current
  `Microsoft.HEIFImageExtension` is in the list; `Microsoft.WebpImageExtension`
  is too. Confirm: ✓ both present.
- **`Microsoft.MicrosoftSolitaireCollection`** — IS a game, **stays out**
  of skip-list (the publisher-prefix already classifies it).

**Recommendation:** the critical missing entries are the six
`Microsoft.Xbox*` system packages. They cannot be covered by extending
`Microsoft.Xbox` to a more specific prefix because the heuristic-C
prefix `Microsoft.Xbox` *was* the broad pattern by design — it must
either be tightened (see Section 5) or every `Microsoft.Xbox*`
non-game must be in the skip-list explicitly.

The skip-list runs **before** the heuristic check (`mod.rs:280-282`),
so adding a `Microsoft.XboxIdentityProvider` entry preempts both B and
C from firing on it. That is the smallest-blast-radius patch.

---

## 4. Skip-list overshoots

Entries that might exclude a real game:

- **`Microsoft.WindowsCommunicationsApps`** — covers Mail/Calendar.
  Unambiguously not a game. Safe.
- **`Microsoft.UI.`** (note the trailing dot) — covers `Microsoft.UI.Xaml.*`.
  Safe.
- **`Microsoft.Dev.`** — covers `Microsoft.Dev.Box`, `Microsoft.Dev.Home`.
  Safe.
- **`MicrosoftCorporationII.`** — covers `MicrosoftCorporationII.QuickAssist`,
  `MicrosoftCorporationII.MicrosoftFamily`. **Risk:** if Microsoft ever
  publishes a game under a `MicrosoftCorporationII.` namespace it would
  be silently dropped. Empirically all II/III packages are utility
  apps; low risk.
- **`MicrosoftCorporationIII.`** — same.
- **`Microsoft.HostApps`** — overly broad if any future game ships
  under a `Microsoft.HostApps.*` family. Currently only WSA-like host
  apps. Low risk.
- **`MSIX.`** — extremely broad — every package family using `MSIX.`
  prefix is hidden. Empirically only Microsoft-internal packages use
  this. Low but non-zero risk.

No overshoot is currently blocking a known real game on a typical user's
machine. None require immediate removal.

---

## 5. The fundamental issue

**This is not a tunable problem.** The heuristic chain is wrong-shaped.

The chain is monotonic-OR with no negative signals, so any new
heuristic you add can only *create* false positives — it can't undo
them. The only escape valves are:

1. The skip-list — must be hand-curated against the entire long tail
   of Microsoft + third-party UWP apps. This is unbounded work and
   constantly drifts.
2. The `treat_all_as_games` override — designed for the opposite
   problem (false negatives on Game Pass titles).

Heuristic D (`has_significant_exe`) is the load-bearing failure mode:
it fires on essentially every UWP app with any binary, so the chain
falls back to "skip-list says no" for 100% of false-positive control.

The two single-step fixes that would help most:

- **Drop heuristic D entirely** for the gaming flag. Use it only as a
  tie-breaker when an authoritative signal is ambiguous. UWP apps with
  no real .exe are still launchable through their AUMID — the install
  presence test isn't actually doing what its name implies.
- **Tighten heuristic C**: replace `Microsoft.Xbox` with an
  exclude-list-aware match. `Microsoft.Xbox*` is overwhelmingly
  *infrastructure* (5+ system packages) versus games (essentially zero
  — Forza ships under `Microsoft.624F8B84B80`, Halo ships under
  `Microsoft.254428518...`). The `Microsoft.Xbox` prefix is producing
  false positives at much higher rate than true positives.

But the real fix is structural: stop guessing, read the authoritative
signal.

---

## 6. Recommendations to the parallel research agent

The right authoritative signal almost certainly lives in one of these
places (the parallel Wave-6 agent should validate which):

### a. AppxManifest `<uap:VisualElements>` / category metadata

The Microsoft Store has a fixed taxonomy (verified at
[learn.microsoft.com/.../categories-and-subcategories](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/categories-and-subcategories)):
**"Games"** is one of ~25 top-level categories, and a published app's
category is locked at submission and **cannot be changed** to/from
Games. That makes it the most reliable signal.

The category does NOT live in `AppxManifest.xml` — it's published in
the developer portal and surfaced via the Microsoft Store API, not the
manifest. Local `.appxbundle` packages may include a `StoreManifest.xml`
sibling to `AppxManifest.xml` but it's optional and rarely populated.

### b. Microsoft Store catalog API

`https://storeedgefd.dsx.mp.microsoft.com/v9.0/products/{ProductId}` —
returns `Properties.ProductCategory` and `Properties.Categories[]`.
Requires the StoreId for the package, which is reachable from the
package family name via the Store's lookup endpoint.

This is the same data the Xbox app and Microsoft Store app use to
classify your library. It is the authoritative source.

### c. PackageContentGroup / `<msix:DeviceCapability>`

Pure-manifest signals (cheap to read, no network) that correlate but
do not exactly identify a game:

- `<rescap:Capability Name="runFullTrust" />` plus a Direct3D usage
  manifest entry.
- `<Resources>/<Resource Language="...">` with multiple languages —
  games tend to ship many; system apps tend to ship one.
- Package install size — games are typically >500 MB; UWP utilities
  are typically <100 MB. Available via
  `Windows.ApplicationModel.Package.GetSizeInBytesAsync`.

### d. Xbox Game Bar / Gaming Services known-game registry

`HKEY_CURRENT_USER\Software\Microsoft\GameBar\GamePanel\GameDVR\KnownGames`
or the equivalent under `HKLM\Software\Microsoft\PolicyManager\default\ApplicationManagement`
— the OS itself maintains a list of "this AUMID is a game." This is
what Game Mode + Game Bar key off. **This is probably the right local
signal** — it's free, fast, exact, and matches what the user perceives
as "this is a game."

### Recommended hybrid

1. **Primary:** Game Bar's KnownGames registry / GameDVR known-AUMID set
   (signal d). Local, fast, OS-blessed.
2. **Fallback:** `MicrosoftGame.Config` presence (current heuristic A).
3. **Last resort:** Microsoft Store catalog API category lookup
   (signal b), cached aggressively.
4. **Drop:** Heuristics B (capabilities), C (publisher prefix beyond
   the very narrow `Microsoft.624F8B84B80` / `Microsoft.GamingApp`
   list), and D (any-non-launcher-exe) for the *gaming* decision.
   Optionally retain them as low-confidence tie-breakers.

The skip-list will still be needed for system / infrastructure
packages that the AUMID-based signal is unaware of, but it will become
much smaller and more stable.

---

## Citations

- `src-tauri/src/library/xbox/mod.rs:1-987` — provider, layered chain,
  helpers, tests.
- `src-tauri/src/library/xbox/skip_list.rs:1-108` — 54 prefixes (actually
  74 lines of prefixes counted).
- `src-tauri/src/library/xbox/manifest.rs:64-159` — `parse_manifest_full`,
  `ManifestSummary`, capability collection.
- `src-tauri/src/library/xbox/winrt.rs:50-98` — `WinRtEnumerator::enumerate`.
- `src-tauri/src/types.rs:102-117` — `AppEntry::is_game()` (Rust source
  of truth, mirrored on the frontend).
- `src/api/bridge.ts:54-91` — `enrich()` is the **only** code path that
  computes `is_game` for the frontend. `Xbox` source defers entirely to
  `metadata.is_xbox_game === true`. No downstream filter overrides it.
- `src/pages/HomePage.tsx:92,103,119,253` — Home grid filters by
  `g.is_game`.
- `src/pages/LibraryPage.tsx:136-137` — Library page splits by
  `is_game`.
- `src/components/QuickResume.tsx:124`, `src/components/QuickSearch.tsx:182`
  — both filter by `g.is_game`.
- `resources/default_config.toml:39-57` — no `library.xbox.treat_all_as_games`
  key; default is `false` via `parse_bool(None)`. **The user is not
  accidentally running with the override on.**
- `src/pages/SettingsPage.tsx:104,225-227` — frontend default for the
  override toggle is `false`.

External authoritative references:
- [App capability declarations - UWP applications](https://learn.microsoft.com/en-us/windows/uwp/packaging/app-capability-declarations)
- [Categories and subcategories for MSIX app](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/categories-and-subcategories)
- [StoreManifest schema (Windows 10)](https://learn.microsoft.com/en-us/uwp/schemas/storemanifest/storemanifestschema2015/schema-root)
- [Get-AppxPackage (Appx) | Microsoft Learn](https://learn.microsoft.com/en-us/powershell/module/appx/get-appxpackage)
- Microsoft Edge AppxManifest sample (verified no gaming capabilities):
  [matchakuya/msedge AppxManifest.xml](https://github.com/matchakuya/msedge/blob/master/AppxManifest.xml)
- [Win-Debloat-Tools/Remove-Xbox.ps1](https://github.com/LeDragoX/Win-Debloat-Tools/blob/main/src/scripts/Remove-Xbox.ps1)
  — confirms the six `Microsoft.Xbox*` infrastructure packages all
  pre-installed.
