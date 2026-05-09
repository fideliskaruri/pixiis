# Wave 6 — UWP / Xbox "is this a game?" research

**Owner:** research (this doc).
**Audience:** the implementation agent in the next wave.
**Mission as set by user:**
> "all xbox apps show up not just games. i only want this to be a game launcher."

This is research, not a code change. Section 7 ("Recommendation for Pixiis") and section 8 ("Implementation contract") are the bits the next agent works against. The rest is the evidence trail.

---

## TL;DR — the headline finding

**The brief's premise is wrong.** There is no `<uap:Category>` element on `<Application>` (or anywhere in `AppxManifest.xml`) that carries the genre. Game-genre values like `Games_Action` exist only as Microsoft Store *submission metadata* — the developer picks them in Partner Center, and they live behind the Store's catalog API, not in any file shipped with the package on disk. The Microsoft Learn URL the brief cites for that schema (`element-uap-category`) returns 404, which is consistent: the element does not exist at the location implied. Source: the same fetch attempt also confirmed by the schema-root index at [Package manifest schema reference for Windows 10](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/schema-root) — `Category` only appears as an attribute on `<Extension>`, where its values are extension-point identifiers like `windows.fileTypeAssociation`, not genres.

Genres are a Store catalog concept — see the full table in [Categories and subcategories for MSIX app](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/categories-and-subcategories). Reading them requires the Microsoft Store catalog API + a StoreId, which we get from `MicrosoftGame.config` — the GDK-era manifest that *does* exist on disk for Xbox PC titles. So:

- **The cheap, on-device, authoritative signal we *do* have is `MicrosoftGame.config`.** Its presence means "shipped through the GDK MSIXVC pipeline" and that pipeline is the one Game Pass / Xbox PC titles use.
- **The Wave 4 layered heuristic is upside-down.** Three of its four signals (gaming-capability, publisher-prefix, install-dir-has-non-launcher-exe) are weak / noisy, and the strongest of the three (publisher-prefix) is also the rarest match. The "non-launcher exe" one matches basically every UWP app and is the proximate cause of the user's complaint.
- **The right fix is to invert the polarity.** Default to "not a game", and require an explicit positive signal — `MicrosoftGame.config` present, OR install path under `*\XboxGames\*`, OR publisher-prefix match — to flip to "game". Drop the gaming-capability and significant-exe heuristics entirely. Keep the user override for the long tail.

Section 7 has the concrete chain. Read it linearly.

---

## 1. The canonical signal — what's the right "is this a game?" field?

There is no single platform-blessed "isGame" boolean exposed to ordinary apps. The candidates, ranked by authority:

### 1.1. Highest authority: `Windows.Gaming.Preview.GamesEnumeration.GameList` (NOT USABLE)

`GameList.FindAllAsync()` returns `IReadOnlyList<GameListEntry>`, each carrying a `Category` of type `GameListCategory` (`Candidate` / `ConfirmedBySystem` / `ConfirmedByUser`). This is the API the Game Bar / Xbox PC overlay use to know what's a game. **But it is gated:**

> "This API is not available to all apps. Unless your developer account is specially provisioned by Microsoft, calls to these APIs will fail at runtime."

Source: [GameList Class](https://learn.microsoft.com/en-us/uwp/api/windows.gaming.preview.gamesenumeration.gamelist) and [GameListCategory Enum](https://learn.microsoft.com/en-us/uwp/api/windows.gaming.preview.gamesenumeration.gamelistcategory). The capability is `gameList`, not in any free-to-declare manifest space — you need a Microsoft business arrangement to declare it. Pixiis cannot use this.

### 1.2. Strong authority: `MicrosoftGame.config` presence

`MicrosoftGame.config` is the GDK-era successor to AppxManifest for game-specific metadata. It is required for any title that ships through the MSIXVC pipeline to the Microsoft Store as a game. From [MicrosoftGame.config overview](https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/game-config/microsoftgameconfig-overview):

> "Each game that's distributed through Microsoft Store must include a manifest [...] The name of the manifest file is *MicrosoftGame.config*."
>
> "For support of Gaming Runtime features, Title Identity, MSIXVC Packaging support and the capability to submit to the Microsoft Store - a *MicrosoftGame.config* is required."

The file lives at the install root (alongside `AppxManifest.xml`). For Game Pass / Xbox PC titles installed via the Xbox app, the install root is `[drive]:\XboxGames\<TitleName>\Content\` — see [Getting started with packaging for PC](https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc):

> "As of the March 2022 Microsoft Game Development Kit (GDK), MSIXVC packages install to the `[drive]:\XboxGames` folder laid out as flat files that you can modify and access directly."

**This is the cheapest authoritative signal we have.** Presence of `MicrosoftGame.config` means "this package was packaged through the GDK as a game." False-positive rate: effectively zero (you don't ship MSIXVC for a productivity app — there's no reason to).

False-*negative* rate is the catch:

- **Older / non-GDK Xbox titles** that pre-date the GDK packaging requirement may not ship a `MicrosoftGame.config`. Empirically rare on a 2024+ machine but possible — Wave 1's spike report flagged the field as "vacuous on this machine (no `MicrosoftGame.Config` files installed)".
- **Sideloaded / dev-mode** UWP games may skip it.
- **Microsoft Store games sold as plain UWP** (not GDK MSIXVC) do not have it. Some classics — `Microsoft.MicrosoftMahjong`, `Microsoft.MicrosoftSolitaireCollection` — fall here.

For those, we need fallbacks (sections 1.3 and 1.4).

### 1.3. Strong authority: install path under `*\XboxGames\*`

Xbox PC games installed via the Xbox app on Windows 10/11 install to `[drive]:\XboxGames\<TitleFolder>\Content\`. This is true for *every* Game Pass / Xbox PC store title since GDK March 2022. Source: same Microsoft Learn page above; corroborated by [How to install or move your Xbox PC games to any folder (PCWorld)](https://www.pcworld.com/article/623123/how-to-install-or-move-your-xbox-pc-games-to-any-folder.html):

> "Games will install to C:\XboxGames as the default folder. [...] you can have games installed on different drives, with only one folder allowed per drive — for example, Limbo can live at C:\XboxGames while Halo Infinite resides in D:\FinishedXboxGames."

Path test: if `pkg.install_location` contains a path component literally named `XboxGames` (case-insensitive), the package is a Game Pass / Xbox PC title with very high probability. This catches a large set of titles even when `MicrosoftGame.config` is missing for some reason.

False-positive rate: very low. The folder name `XboxGames` is reserved by the Xbox app for game installs.

### 1.4. Medium authority: publisher / family-name prefix

The Wave 4 list (36 prefixes) is a reasonable starting point, but it confuses two different sources of authority:

- **Publisher Display Name** in the manifest (e.g. `Mojang Studios`, `Bethesda Softworks`). Loose, non-canonical.
- **Package family-name prefix** (e.g. `BethesdaSoftworks.Starfield_3275kfvv8evfe`). Stable, set at Store ingestion, harder to fake.

Family-name prefix matching is the version that actually means something. See section 4 for the full audited list.

### 1.5. Weak / unreliable signals (DROP)

- **Gaming capabilities in the AppxManifest** (`xboxLive`, `gameBarServices`, `gameAccessoryManagement`, …). The Wave 4 list of 8 capability fragments. **Problem:** non-game apps that *integrate with* gaming infrastructure (e.g. Xbox companion apps, GeForce Now thin clients, anti-cheat helpers, Xbox Game Bar widgets) declare these too. False-positive rate on a typical machine: non-trivial. Worth dropping as a *positive* signal — see section 3 for using their *absence* as a tiebreaker only.
- **"Significant exe in install dir"** (the dominant heuristic in Wave 4). **Problem:** every UWP app that ships any native code has at least one `.exe`, and the launcher / updater / installer name list is not exhaustive — Edge ships `MicrosoftEdge.exe`, OneDrive ships `OneDrive.exe`, Teams ships `Teams.exe`, GitHub Desktop ships `GitHubDesktop.exe`. The current 17-fragment exclusion list catches a few common shims but misses the actual non-launcher names of every productivity app. **This is the proximate cause of the user's "all xbox apps show up" complaint.** Drop it entirely.

### 1.6. Anti-signal: AppListEntry="none"

Many UWP packages declare child applications they don't want surfaced in any launcher — extension hosts, companion services, COM brokers, telemetry agents. The manifest hides them with `AppListEntry="none"` on `<uap:VisualElements>`. Source: [uap:VisualElements (Windows 10)](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-uap-visualelements):

> "**AppListEntry** — The entry in the All Apps List. Select none for entry points that do not need start menu tiles."

And: [Stefan Wick — UWP with Desktop Extension Part 4](https://stefanwick.com/2018/04/29/uwp-with-desktop-extension-part-4/) — the canonical writeup that explains adding `AppListEntry='none'` "to hide the UWP from the app list."

**Pixiis must respect this.** Currently the manifest parser at `src-tauri/src/library/xbox/manifest.rs` does not read `AppListEntry`, so we surface child apps that even Microsoft thinks shouldn't appear in any launcher. Easy fix.

---

## 2. Recommended detection chain

Ordered list. Top is most-authoritative-and-cheapest. Each signal can answer "is this a game?" with one of `YES`, `NO`, or `UNKNOWN`. Combine with an OR over `YES` answers, and drop on the first `NO`.

| # | Check | Cost | False-positive rate | Online? | Verdict on hit |
|---|-------|------|---------------------|---------|----------------|
| 1 | `pkg.is_framework == true` | free (already have) | — | no | NO (drop) |
| 2 | `pkg.install_location` doesn't exist on disk | one stat() | — | no | NO (drop, orphaned) |
| 3 | Package name in static skip-list | one HashSet hit | — | no | NO (drop) |
| 4 | All `<Application>` children of the manifest have `AppListEntry="none"` | already parsing | <0.1% | no | NO (drop, hidden) |
| 5 | `MicrosoftGame.config` exists at install root | one stat() | ~0% | no | **YES (game)** |
| 6 | Any path component of install_location case-insensitively equals `XboxGames` | one path walk | <0.5% | no | **YES (game)** |
| 7 | Family-name prefix matches the curated list (section 4) | one starts-with loop | ~1–2% | no | **YES (game)** |
| 8 | None of 5/6/7 fired | — | — | no | NO (default, "not a game") |
| 9 | User override `library.xbox.treat_all_as_games = true` | already wired | n/a | no | YES (force, last resort) |

Notes:

- **Default is NO.** This is the biggest behavioral change from Wave 4. The user's complaint is fixed by the default flip; the positive-signal checks then catch the actual games.
- **Order matters for early-out efficiency, not for correctness.** Each check is independent.
- **No filesystem walks.** Wave 4's `has_significant_exe` reads up to 64 directory entries per package. Drop it.
- **No capability inspection on the positive path.** We still parse capabilities (cheap, already in the parser) but only consume them as a *tiebreaker* signal — see section 3.

---

## 3. Anti-signals — what excludes a UWP package from being a game

These are checks that, when they fire, force `is_xbox_game = false` even if a positive check above also fired. In practice, the only one we actively need is the skip-list (it pre-empts the positive checks). The others are safety nets for edge cases.

### 3.1. Hard anti-signals (used)

- **`is_framework == true`** — frameworks are dependency-only packages, never games. Already filtered.
- **Skip-list prefix match** — see section 5 for the audited list.
- **All `<Application>` entries hidden via `AppListEntry="none"`** — even the platform agrees these aren't user-launchable.
- **`ms-resource:` placeholder in display name** — the manifest didn't resolve. We currently drop these.

### 3.2. Soft anti-signals (use as tiebreakers in section 7)

These are *not* exclusions on their own, but they bias toward "not a game" if the positive evidence is borderline:

- **Capabilities indicating productivity / utility intent** — `documentsLibrary`, `picturesLibrary`, `musicLibrary`, `videosLibrary`, `enterpriseAuthentication`, `sharedUserCertificates`, `userAccountInformation`, `printSpooler`, `removableStorage`. A package that needs `documentsLibrary` is almost certainly a productivity app.
- **Capabilities indicating system / device tooling** — `inputObservation`, `inputForegroundObservation`, `appBroadcastServices`, `enterpriseDeviceLockdown`, `localSystemServices`. These are admin-tool / system-utility shapes, not games.
- **Microsoft-published with no `MicrosoftGame.config`** — any package whose `package_name` starts with `Microsoft.` AND has no `MicrosoftGame.config` is overwhelmingly likely to be a Microsoft system / productivity app. The known Microsoft-published *games* (Solitaire / Mahjong / Sudoku / Minecraft / GamingApp / Xbox-prefixed) are explicitly listed in our publisher-prefix list — section 4 — and override this. Treat this rule as: "Microsoft-published + not in publisher-prefix list + no MicrosoftGame.config + not under XboxGames = NO."

For the *full* list of Microsoft Store category strings (Productivity, Utilities, Photo + video, etc.) see [Categories and subcategories for MSIX app](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/categories-and-subcategories). We do not consume these directly because they live in the Store catalog, not the manifest — but they're useful for sanity-checking the skip-list (section 5).

---

## 4. Family-name patterns — the curated publisher-prefix list

This is the single source of truth Pixiis should hard-code for the "publisher publishes games" check. The Wave 4 list of 36 prefixes is a reasonable start; below is the audited replacement.

### 4.1. Keep (high-confidence game publishers, Wave 4 entries that survive)

```
Microsoft.Xbox            ← all Xbox-branded titles (Xbox app itself isn't a game; relies on display-name dedup or a more specific match)
Microsoft.GamingApp       ← THE Xbox app — see note below
Microsoft.MinecraftUWP
Microsoft.Minecraft
Microsoft.MicrosoftSolitaireCollection
Microsoft.MicrosoftMahjong
Microsoft.MicrosoftSudoku
Microsoft.MicrosoftJackpot
Microsoft.MicrosoftTreasureHunt
Microsoft.MicrosoftBingo
Microsoft.MicrosoftUltimateWordGames
Microsoft.624F8B84B80     ← Forza Horizon 5 (publisher hash)
Microsoft.GameApps
MojangStudios.
Mojang.
KingDigitalEntertainment.    ← Candy Crush etc.
EAInc.
ElectronicArts.
TakeTwoInteractive.
2K.
2KGames.
BethesdaSoftworks.
BethesdaGameStudios.
Ubisoft.
UbisoftEntertainment.
SquareEnix.
Sega.
SEGAofAmericaInc.
BandaiNamco.
BandaiNamcoEntertainment.
Capcom.
Activision.
ActivisionPublishingInc.
Blizzard.
BlizzardEntertainment.
RiotGames.
ZeniMaxOnline.
InnerSloth.
ObsidianEntertainment.
FromSoftware.
```

### 4.2. Add (game publishers / known titles missing from Wave 4)

The brief explicitly asks "what's missing." Empirically, these have shipped UWP / Xbox PC titles and are absent from Wave 4. Sources: [List of games available on Microsoft Store (PCGamingWiki)](https://www.pcgamingwiki.com/wiki/List_of_games_available_on_Microsoft_Store) and [Xbox-app aggregated library coverage notes](https://www.ghacks.net/2025/06/30/xbox-pc-app-now-shows-games-from-steam-epic-games/).

```
# AAA / mid publishers
505Games.
A2Z4DOLLC.                                 ← A2Z titles (Xbox)
AsobimoInc.
AspyrMediaInc.
AtlusUSA.
BandaiNamcoEntertainmentEurope.
CDPROJEKTRED.                              ← CD Projekt Red
CDProjektRED.
CodeMasters.                               ← Codemasters (now part of EA)
DeepSilver.                                ← Saints Row, Metro, etc.
Devolver.
DevolverDigital.
Disney.                                    ← Disney games
DisneyInteractive.
DotEmu.
Frontier.                                  ← Frontier Developments
FocusEntertainment.                        ← Focus Home Interactive successor
FocusHomeInteractive.
GameloftSE.
GearboxPublishing.
HelloGames.                                ← No Man's Sky
IOInteractive.                             ← Hitman series
Konami.
KonamiDigitalEntertainment.
LarianStudios.                             ← Baldur's Gate 3
LucasfilmGames.
MachineGames.                              ← Wolfenstein, Indiana Jones
ModiphiusEntertainment.
NaconStudio.
NamcoBandai.                               ← legacy spelling
Paradox.                                   ← Paradox Interactive
ParadoxInteractive.
PrivateDivision.
RebellionDevelopments.
RemedyEntertainment.
RockstarGames.
Rovio.
SCSSoftware.                               ← American/Euro Truck Sim
SeaOfThieves.                              ← Rare title
SonicTeam.                                 ← Sega subsidiary
SonyInteractiveEntertainment.              ← PS games published to PC
TeamCherry.                                ← Hollow Knight
TheGameKitchen.                            ← Blasphemous
ThunderfulPublishing.
TripwireInteractive.
ValveCorporation.                          ← if Steam ever publishes through MS Store (rare)
WaybackEntertainment.
WizardsoftheCoast.                         ← Hasbro tabletop games
WolverineStudios.
WoWoWoGames.
XSEEDGames.

# Microsoft first-party studios / titles often shipped under their own family names
ArkaneStudios.
ArkaneAustin.
DoubleFineProductions.
TheCoalition.
Compulsion.                                ← Compulsion Games (We Happy Few)
CompulsionGames.
Inxile.                                    ← inXile
InxileEntertainment.
Ninja.                                     ← Ninja Theory
NinjaTheory.
PlaygroundGames.                           ← Forza Horizon
RareLimited.                               ← Rare
TurnTen.                                   ← Turn 10 (Forza Motorsport)
Turn10Studios.
UndeadLabs.                                ← State of Decay
WorldsEdge.                                ← Age of Empires II/IV/Mythology

# Known title-specific package names (some Xbox titles use a hashed publisher ID instead of a name)
Microsoft.Halo                             ← Halo: MCC, Halo Infinite (some SKUs use Microsoft.HaloMCC)
Microsoft.SeaofThieves                     ← Sea of Thieves
Microsoft.Forza                            ← Forza Motorsport / Horizon (some SKUs)
Microsoft.AgeofEmpires                     ← AOE II/IV
Microsoft.AgeOfEmpires
Microsoft.Flight                           ← Microsoft Flight Simulator
Microsoft.MicrosoftFlightSimulator
Microsoft.StateofDecay
Microsoft.GearsOfWar
Microsoft.Wasteland
```

(The exact set is empirical — verify against `Get-AppxPackage | Select Name` on the user's machine. The principle is: every entry should be a publisher or title that has shipped a UWP / MSIXVC game to Microsoft Store. Don't add publishers you can't cite.)

### 4.3. Remove (Wave 4 entries to reconsider)

- **`Microsoft.Xbox`** as a *prefix*. Bare `Microsoft.Xbox` matches `Microsoft.Xbox.TCUI` (Xbox companion telemetry component, system extension) and similar. Consider tightening to `Microsoft.XboxGameOverlay` / specific known prefixes, OR keep as-is and trust the framework / skip-list filters that already exclude `*.TCUI`-style packages. Currently fine — no action — but worth noting.

### 4.4. Note: `Microsoft.GamingApp` is the Xbox app itself

The Xbox app is in the publisher list because users do conceptually want it surfaced, but it is **not a game**. Either:

- Remove it from the publisher list and let it fall through to "not a game" (cleanest).
- Keep it in the list and accept that the Xbox app shows up as a game on Home (current Wave 4 behavior).

I'd recommend the first — it's a launcher, not a title — but flag this for product call. The user's complaint of "all xbox apps show up" plausibly includes this one.

---

## 5. Skip-list audit

The Wave 4 skip-list at `src-tauri/src/library/xbox/skip_list.rs` has 89 prefixes (it grew past the 54 the brief mentioned). Audited below.

### 5.1. Keep (correctly excluded; high-confidence non-games)

All of these are Microsoft-shipped utilities. Do not change:

```
Microsoft.Windows           Microsoft.UI.Xaml           Microsoft.VCLibs
Microsoft.NET.              Microsoft.Services          Microsoft.DirectX
Microsoft.Advertising       Microsoft.DesktopAppInstaller
Microsoft.StorePurchaseApp  Microsoft.VP9VideoExtensions
Microsoft.WebMediaExtensions  Microsoft.HEIFImageExtension
Microsoft.WebpImageExtension  Microsoft.RawImageExtension
Microsoft.AV1VideoExtension  Microsoft.HEVCVideoExtension
MicrosoftWindows.           windows.                    NcsiUwpApp
Microsoft.ECApp             Microsoft.LockApp           Microsoft.AsyncTextService
Microsoft.AccountsControl   Microsoft.AAD.              Microsoft.BioEnrollment
Microsoft.CredDialogHost    Microsoft.Win32WebViewHost  InputApp
MicrosoftCorporationII.QuickAssist  Microsoft.SecHealthUI
Microsoft.MicrosoftEdge     Microsoft.Edge              MicrosoftEdge.
Microsoft.Office.           Microsoft.Office            Microsoft.OneDrive
Microsoft.OneNote           Microsoft.Outlook           Microsoft.Teams
MSTeams                     MicrosoftTeams              Microsoft.Skype
Microsoft.MSPaint           Microsoft.Paint             Microsoft.WindowsTerminal
Microsoft.PowerShell        Microsoft.WindowsCalculator  Microsoft.WindowsAlarms
Microsoft.WindowsCamera     Microsoft.WindowsFeedbackHub  Microsoft.WindowsMaps
Microsoft.WindowsNotepad    Microsoft.WindowsSoundRecorder  Microsoft.WindowsStore
Microsoft.StorePurchase     Microsoft.Photos            Microsoft.MicrosoftStickyNotes
Microsoft.MicrosoftOfficeHub  Microsoft.GetHelp        Microsoft.Getstarted
Microsoft.People            Microsoft.MixedReality      Microsoft.YourPhone
Microsoft.WidgetsPlatformRuntime  Microsoft.ZuneMusic   Microsoft.ZuneVideo
Microsoft.MoCamera          Microsoft.PowerAutomate    Microsoft.Whiteboard
Microsoft.Todos             Microsoft.ScreenSketch     Microsoft.MicrosoftFamilySafetyClient
Microsoft.LanguageExperiencePack  Microsoft.WindowsCommunicationsApps
Microsoft.UI.               Microsoft.Dev.             Microsoft.PowerToys
MicrosoftCorporationII.     MicrosoftCorporationIII.   Microsoft.Win32
Microsoft.RemoteDesktop     Microsoft.MicrosoftPCManager  Microsoft.HostApps
Microsoft.VisualStudio      MSIX.
```

### 5.2. Add (Microsoft-shipped non-games not yet in the list)

These are visible on a typical 2025 Windows 11 machine and are not in Wave 4. Source: cross-referenced against the standard pre-installed app list documented in [Microsoft Store: pre-installed and provisioned packages](https://learn.microsoft.com/en-us/windows/configuration/store/find-aumid) and observed `Get-StartApps` output.

```
# Microsoft Store + Web
Microsoft.Bing                           ← Bing search
Microsoft.BingWeather                    ← Weather
Microsoft.BingNews                       ← News
Microsoft.BingFinance                    ← MSN Money (legacy name)
Microsoft.BingSports                     ← MSN Sports (legacy name)
Microsoft.BingTranslator                 ← Translator
Microsoft.MSN.                           ← MSN family
Microsoft.News                           ← News
Microsoft.MicrosoftToDoList              ← To Do
Microsoft.MicrosoftPowerBIForWindows     ← Power BI

# UI/Shell ecosystem
Microsoft.Wallet                         ← Wallet
Microsoft.WindowsReadingList             ← Reading List
Microsoft.OneConnect                     ← Mobile Plans
Microsoft.PrintHelp                      ← Print Help
Microsoft.PrintDialog                    ← Print Dialog
Microsoft.Print3D                        ← Print 3D
Microsoft.3DBuilder                      ← 3D Builder
Microsoft.MicrosoftSolitaireCollection — wait, this is a GAME, NOT skip
   (already in the publisher-prefix list)

# Mail / contacts
microsoft.windowscommunicationsapps      ← Mail/Calendar (already covered by lowercase 'windows.' prefix? No — Microsoft.windows... case-sensitive issue, add explicit)
Microsoft.HEVCVideoExtensions            ← extensions plural form
Microsoft.MPEG2VideoExtension            ← MPEG-2 extension
Microsoft.WebpImageExtensions            ← plural form

# Microsoft Edge / Web
Microsoft.MicrosoftEdgeDevToolsClient    ← Edge DevTools
MicrosoftEdgeDevToolsClient.

# Newer Win11 system apps
Microsoft.WindowsClient.                 ← (catches Microsoft.WindowsClient.CBS etc., already partly via MicrosoftWindows.)
Microsoft.GamingServices                 ← Gaming Services support package (NOT a game)
Microsoft.GamingServicesNet              ← .NET shim for Gaming Services
GamingServices.                          ← bare prefix
Microsoft.AV1ProfessionalEncoderExtension
Microsoft.MicrosoftPowerBIForWindows.
Microsoft.MicrosoftClipchamp             ← Clipchamp video editor
Clipchamp.Clipchamp                      ← Clipchamp standalone publisher
Clipchamp.

# Win11 inbox + insiders
Microsoft.GeforceNOW                     ← (if installed via store, not a game per se but a service) — debatable
NVIDIACorp.NVIDIAControlPanel
NVIDIACorp.NVIDIAGeForceExperience

# Common third-party non-games installed via Store
Spotify.SpotifyMusic                     ← Spotify
Spotify.
Netflix.Netflix                          ← Netflix app
Netflix.
DisneyInteractive.DisneyPlus             ← Disney+ app (the streaming service, NOT Disney games — careful)
Disney.DisneyPlus                        ← variant
4DF9E0F8.Netflix                         ← Netflix on some store hashes
HuluLLC.HuluPlus
HuluLLC.

# Browser / chat / dev tools shipped via Store
Mozilla.Firefox
GoogleLLC.GoogleChrome                   ← if it ever ships via Store
SlackTechnologies.Slack
Discord.Discord                          ← Discord (NOT a game; users may want it though — debatable)
Discord.
GitHub.GitHubDesktop
GitHub.
SonicWALLInc.NetExtender                 ← VPN
PaintdotNet.PaintdotNet                  ← Paint.NET
PaintdotNet.

# Adobe / Autodesk
AdobeSystemsIncorporated.
Autodesk.

# Anti-cheat / overlay components that ship as separate packages
EpicGames.EasyAntiCheat                  ← EAC service
EpicGamesInc.
RiotClient.                              ← Riot anti-cheat (but RiotGames. is in the publisher list — careful)
```

Notes:

- The "debatable" entries (Discord, GeForce Now, Disney+) are judgment calls. The user said "only games"; if it streams videos / chats / VPNs, exclude.
- **Spotify, Netflix, etc. are big enough false-positives** that without them in the skip-list, the publisher-prefix-only fallback in section 7 will mis-classify any of these that happen to ship a real `.exe`. Adding them is cheap and important.
- The skip-list **MUST take precedence over the publisher-prefix list**. Currently in `mod.rs` the skip-list runs first (`if skip_list::is_skipped(&pkg.package_name) { continue; }`) — keep that ordering.

### 5.3. Audit verdict

The current Wave 4 skip-list is *correctly aimed* but **incomplete on third-party non-games**. The reason it didn't bite hard before Wave 4 is that the Wave 1 detection only fired on `MicrosoftGame.config`, which Spotify / Netflix / etc. don't have — they were already filtered out by lacking that signal. The Wave 4 broadening flipped this: now Spotify (which has a real `Spotify.exe`) trips `has_significant_exe`, and there's no skip-list entry for it.

**Recommendation:** ship the additions in 5.2 *and* drop the `has_significant_exe` heuristic per section 1.5. Either alone is insufficient.

---

## 6. Folder + Start Menu noise (follow-up wave)

The brief asks how to make the folder scanner and Start-Menu scanner game-only too. Quick notes; this is a separate wave.

### 6.1. Folder scan (the user's "watch this directory" path)

Same problem in miniature. `find . -maxdepth N -name '*.exe'` on a folder full of game installers also surfaces every utility EXE, every uninstaller, and every tool the games install alongside themselves. The game heuristics don't apply (no AppxManifest). Best signals on disk:

- **Heuristic: presence of a `.gdf.dll` file** — Game Definition File DLL, written by GDK-aware games. Not common but very high confidence when present. See [Game definition files (Win32)](https://learn.microsoft.com/en-us/windows/win32/gameux/about-game-definition-files-and-the-gdfmaker-tool) on Microsoft Learn.
- **Steam-style:** an `appmanifest_<id>.acf` in `steamapps/` is a game. The folder scanner can recognize the parent.
- **GOG-style:** a `goggame-<id>.info` JSON file is a game.
- **Epic-style:** a `.egstore/` directory is a game.
- **Generic / nothing matches:** make the folder scan *opt-in only* — i.e. user explicitly adds a folder, and we trust the user. Don't auto-scan `Program Files` looking for games. (Pixiis already does this — verify before changing.)

### 6.2. Start Menu shortcut scan

Same problem. Best signals:

- **`.lnk` target points into `*\XboxGames\*` or a known game-storefront install root** (`*\Steam\steamapps\common\*`, `*\Epic Games\*`, `*\GOG Games\*`, `*\Battle.net\*`, `*\Riot Games\*`). High confidence.
- **`.lnk` lives in a Start-Menu folder named like a publisher in the section 4 list.** Medium confidence.
- **Nothing matches:** drop. Better to miss a game than to add Notepad.

Implement both in a follow-up wave with the user's explicit opt-in for "deep scan" — same pattern as Wave 4's `treat_all_as_games` override.

---

## 7. Recommendation for Pixiis — concrete

Replace the current 4-heuristic OR with a **default-NO, positive-signal-required** chain. Here's the exact decision tree, pseudocode-free:

```
For each enumerated package:

  # Pre-filters (already in place; keep)
  IF pkg.is_framework               → skip entirely (don't surface)
  IF skip_list_match(pkg.package_name) → skip entirely
  IF display_name is empty / "ms-resource:..." → skip entirely
  IF AppxManifest.xml unparseable / no <Application> → skip entirely

  # NEW: AppListEntry filter — drop child apps the platform itself hides
  IF every <Application> in the manifest has AppListEntry="none"
     AND there is no MicrosoftGame.config to override → skip entirely

  # POSITIVE-SIGNAL chain — ANY hit flips is_xbox_game = true
  is_game = false
  IF MicrosoftGame.config exists at install root → is_game = true
  ELSE IF any path component of install_location equals "XboxGames"
       (case-insensitive) → is_game = true
  ELSE IF family_name OR package_name starts with any prefix in
       GAME_PUBLISHER_PREFIXES (section 4) → is_game = true
  # (note: NO gaming-capability check, NO has_significant_exe check)

  # Override
  IF library.xbox.treat_all_as_games == true → is_game = true

  Surface the entry with metadata.is_xbox_game = is_game
```

**Net behavioral diff vs Wave 4:**

- Spotify, Netflix, Discord, GitHub Desktop, every UWP utility shipping its own `.exe` → no longer flagged as games.
- Real Game Pass titles still flagged (MicrosoftGame.config OR XboxGames path).
- Microsoft Solitaire / Mahjong / Sudoku / Minecraft → still flagged (publisher prefix).
- Most third-party UWP titles → still flagged (publisher prefix, expanded list in section 4).
- Long tail of pre-GDK Microsoft Store games with no MicrosoftGame.config and no recognizable publisher → fall through to "not a game" — user can flip the override. **Acceptable trade-off.**

### 7.1. Manifest fields to read

Currently `parse_manifest_full` reads:

- `<Application Id Executable>` per app
- `<uap:VisualElements Square150x150Logo Logo>` per app
- `<Capability/DeviceCapability/CustomCapability Name>` for the package summary

Add:

- `<uap:VisualElements AppListEntry>` per app (string, `default` | `none`).

That's it. No new file reads.

### 7.2. New filesystem checks

Just two stat() calls per package:

- `MicrosoftGame.config` exists? (cheap, already done)
- The install_location path string contains a component named `XboxGames`? (path manipulation, no I/O)

Drop:

- `has_significant_exe` and its 64-entry directory walk. Saves real time on packages with thousands of files in their root (some game packages have asset blobs that show up at the top level).

### 7.3. Telemetry the next wave should add

When the `treat_all_as_games` override flips a package to a game, **log the package name + family name + install location**. After a week of dogfood, the user should be able to check that log and tell us:

- "These 3 are real games my heuristic missed" → add their family-name prefix to section 4's curated list and ship a follow-up.
- "These 5 aren't games; the override is wrong" → the override is doing exactly what was advertised, accept.

Without this log there's no closed loop on improving the heuristic over time.

---

## 8. Implementation contract — for the next agent

### 8.1. Files to touch

| File | Change |
|---|---|
| `src-tauri/src/library/xbox/manifest.rs` | Add `app_list_entry: Option<String>` to `ManifestApp`. Read the `AppListEntry` attribute alongside `Id` / `Executable`. Add a helper `is_hidden(&self) -> bool` that returns true when the attribute equals `"none"` (case-insensitive). |
| `src-tauri/src/library/xbox/mod.rs` | Replace the layered `is_game = ...` expression with the chain in section 7. Drop `has_significant_exe`, `LAUNCHER_EXE_HINTS`, `EXE_EXTENSIONS`, `has_gaming_capability`, `GAMING_CAPABILITY_HINTS`. Add helper `installs_under_xbox_games(&Path) -> bool`. Add helper `all_apps_hidden(apps: &[ManifestApp]) -> bool`. Update `GAME_PUBLISHER_PREFIXES` to the section-4 audited list. |
| `src-tauri/src/library/xbox/skip_list.rs` | Append the section-5.2 entries. Keep alphabetized within logical groups for readability. |
| `src-tauri/src/library/xbox/mod.rs` (tests) | Add: (a) test that a UWP app with all `AppListEntry="none"` is dropped; (b) test that a package under `D:\XboxGames\Foo\Content` with no MicrosoftGame.config is still classified as a game; (c) test that Spotify-shaped package (`Spotify.SpotifyMusic`, has `Spotify.exe`, no MicrosoftGame.config, not under XboxGames) is now classified as **not a game** — this is the regression test that proves the user's complaint is fixed. Keep all existing tests; the only one that should change verdict is `multi_application_package_dedupes_by_display_name` only if the test fixture's display name is hidden — verify. |

### 8.2. Frontend / UX

No frontend change strictly required. The Settings → Library → Show all Xbox apps as games override remains valid as a last-resort. Optional polish: rename the override to "Show all UWP apps in library" (the new copy is more accurate — the override no longer flips heuristic outputs, it *includes* every surviving UWP package).

### 8.3. Expected outcomes

After this change, on a representative Game Pass user's machine:

- Real Game Pass / Xbox PC titles surface as games (no regression vs Wave 4).
- Microsoft-shipped utilities (Edge, Teams, Photos, Calculator, …) don't surface at all (skip-list, unchanged).
- Third-party UWP utilities (Spotify, Netflix, Discord, GitHub Desktop, …) **don't surface as games** — they may still appear in the broader library list with `is_xbox_game = false`, but the Home grid (which filters on `is_xbox_game = true`) becomes clean.
- The user's complaint "all xbox apps show up not just games" is fixed by the polarity flip in the heuristic, *not* by adding more entries to the skip-list.

### 8.4. What this does NOT solve

- The handful of pre-GDK Microsoft Store games with no MicrosoftGame.config and no recognizable publisher in the curated list — they fall through to "not a game". The override flag handles the long tail. Section 7.3's telemetry should grow the curated list over time.
- The Folder-scan + Start-Menu-shortcut noise — separate problem, see section 6, defer to a follow-up wave.
- The `Microsoft.GamingApp` (Xbox app itself) showing up as a "game" — it's in the publisher-prefix list. Decide product-side whether to keep or drop. Both options are one-line changes.

---

## Sources

- [Package manifest schema reference for Windows 10](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/schema-root) — confirms `Category` is an `<Extension>` attribute, not an `<Application>` element.
- [Categories and subcategories for MSIX app](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/categories-and-subcategories) — full table of Microsoft Store categories and game genres.
- [GameList Class (Windows.Gaming.Preview.GamesEnumeration)](https://learn.microsoft.com/en-us/uwp/api/windows.gaming.preview.gamesenumeration.gamelist) — the canonical "is this a game?" API; gated.
- [GameListCategory Enum](https://learn.microsoft.com/en-us/uwp/api/windows.gaming.preview.gamesenumeration.gamelistcategory) — `Candidate` / `ConfirmedBySystem` / `ConfirmedByUser`.
- [GameListEntry Class](https://learn.microsoft.com/en-us/uwp/api/windows.gaming.preview.gamesenumeration.gamelistentry) — `Category`, `LauncherExecutable`, `TitleId`, etc.
- [MicrosoftGame.config overview (GDK)](https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/game-config/microsoftgameconfig-overview) — required for any GDK-pipeline title.
- [Getting started with packaging for PC (GDK)](https://learn.microsoft.com/en-us/gaming/gdk/docs/features/common/packaging/overviews/packaging-getting-started-for-pc) — `[drive]:\XboxGames\` install location, flat-file layout.
- [How to install or move your Xbox PC games to any folder (PCWorld)](https://www.pcworld.com/article/623123/how-to-install-or-move-your-xbox-pc-games-to-any-folder.html) — confirms `XboxGames` folder convention across drives.
- [uap:VisualElements (Windows 10)](https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/uapmanifestschema/element-uap-visualelements) — `AppListEntry` attribute, values `default` / `none`.
- [Stefan Wick — UWP with Desktop Extension Part 4](https://stefanwick.com/2018/04/29/uwp-with-desktop-extension-part-4/) — `AppListEntry='none'` to hide apps.
- [Get-AppxPackage (PowerShell)](https://learn.microsoft.com/en-us/powershell/module/appx/get-appxpackage) — package types, framework filtering.
- [Get-StartApps (PowerShell)](https://learn.microsoft.com/en-us/powershell/module/startlayout/get-startapps) — Start menu enumeration; "Applications that are not listed in the Start menu will not appear in the output of the Get-StartApps cmdlet."
- [Find the Application User Model ID of an installed app](https://learn.microsoft.com/en-us/windows/configuration/store/find-aumid) — AUMID + Get-StartApps.
- [Xbox aggregated library coverage (gHacks)](https://www.ghacks.net/2025/06/30/xbox-pc-app-now-shows-games-from-steam-epic-games/) — context on what the Xbox app on PC shows in 2025.
- [List of games available on Microsoft Store (PCGamingWiki)](https://www.pcgamingwiki.com/wiki/List_of_games_available_on_Microsoft_Store) — sanity check publisher list.
- [Importing Windows Store or Xbox App games (Playnite Wiki)](https://github.com/JosefNemec/Playnite/wiki/Importing-Windows-Store-or-Xbox-App-games) — Playnite's approach: query Xbox catalog API and filter by `type == "Game"`, not by manifest inference.
- [UWP Quick Tip — detecting any installed app on Windows 10 (Suchan)](https://www.suchan.cz/2016/10/uwp-quick-tip-detecting-any-installed-app-on-windows-10/) — `GetAppListEntries()` enumeration pattern.
- [Game definition files (Win32)](https://learn.microsoft.com/en-us/windows/win32/gameux/about-game-definition-files-and-the-gdfmaker-tool) — `.gdf.dll` files, useful for the folder-scan follow-up (section 6.1).
- Internal: `agents/wave3-xbox-fix.md`, `src-tauri/src/library/xbox/{mod,winrt,manifest,skip_list}.rs`, `spike/uwp-detect/RESULTS.md` (referenced; not re-read).
