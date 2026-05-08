# SMOKE.md — Pixiis manual verification runbook

A walk-through to run after any release-candidate build. If a step fails,
follow the **on failure** hint and stop — do not skip ahead.

Time budget: ~10 minutes for the full pass on a warm machine.

Build under test: `src-tauri\target\release\bundle\nsis\Pixiis_*.exe`
(installer) or the dev shell launched via `./build.sh dev`.

---

## 1. Startup

- [ ] App launches from the Start Menu shortcut or installer "Run now"
- [ ] No Windows crash dialog, no Tauri "WebView2 missing" prompt
- [ ] Splash → main window in **< 2 s** on a warm cache
- [ ] Main window opens at 1280×800, frameless, dark background

**How to test:** double-click the Start Menu shortcut. Stopwatch from
click to first paint of the Home grid.

**Expected:** Home page renders with games (or the empty state if no
scan has run yet). No console error toasts.

**On failure:** check `%APPDATA%\pixiis\logs\` for a panic; re-run from
a terminal to capture stderr; confirm WebView2 runtime is installed.

---

## 2. Window controls

- [ ] Minimize button hides to taskbar
- [ ] Maximize toggles between 1280×800 and full-screen-of-display
- [ ] Close button hides to tray (does **not** quit — see section 15)
- [ ] **F11** toggles fullscreen
- [ ] Double-click on the navbar (away from any button) toggles maximize

**How to test:** click each control; tap F11; double-click the empty
strip of the navbar.

**Expected:** every action has a visible response within one frame; no
ghost windows left behind.

**On failure:** check `tauri.conf.json` window decorations and the
custom titlebar event wiring in `src/components/NavBar.tsx`.

---

## 3. Window drag

- [ ] Grab the navbar (away from buttons / search input) and drag — the
      window follows the cursor
- [ ] Releasing inside another monitor lands the window on that monitor
- [ ] Dragging from a button does **not** move the window (button still
      receives the click)

**How to test:** left-mouse-down on the empty navbar strip, drag, release.

**Expected:** smooth drag with no rubber-banding; the HTML drag region
(`data-tauri-drag-region`) covers only non-interactive navbar area.

**On failure:** inspect the navbar element — `data-tauri-drag-region`
should be on the container, not on buttons.

---

## 4. Onboarding (first launch only)

- [ ] Delete `%APPDATA%\pixiis\` entirely, then launch — onboarding fires
- [ ] Step 1 (Welcome) → Next advances
- [ ] Step 2 (Library scan) — runs a scan, shows per-provider counts
- [ ] Step 3 (Voice mic test) — mic level meter responds to speech
- [ ] Step 4 (Controller test) — pressing any face button is detected
- [ ] Step 5 (Done) — "Open Pixiis" navigates to `/` (Home)
- [ ] After completion, `%APPDATA%\pixiis\.onboarded` exists
- [ ] Restart the app — onboarding does **not** fire again

**How to test:** quit Pixiis, `Remove-Item -Recurse -Force "$env:APPDATA\pixiis"`,
relaunch.

**Expected:** all five steps reachable; "Open Pixiis" lands on the Home
grid; the marker file persists across restart.

**On failure:** check the onboarding sentinel logic in the setup hook
(`src-tauri/src/lib.rs`) and the redirect at `/onboarding`.

---

## 5. Library scan

- [ ] Settings → **Scan Now** triggers a scan
- [ ] Per-provider toast or summary lists Steam / Xbox / Epic / GOG / EA
      / Start Menu / Folder / Manual counts
- [ ] Total count matches expectations for the test machine
- [ ] `%APPDATA%\pixiis\scan_debug.log` has one line per provider with
      `(NNNms)` timing

**How to test:** open Settings, click **Scan Now**, wait for the toast.
Open `scan_debug.log` and confirm timings.

**Expected:** scan completes in **< 5 s** on a typical box; no provider
panics surface as a red toast.

**On failure:** read `scan_debug.log` for the offending provider; cross-
check installed storefronts; ensure registry / filesystem permissions
are intact.

---

## 6. Home displays games

- [ ] Home grid renders cards with cover art (RAWG-hydrated where
      possible)
- [ ] Only **games** appear — no random Start Menu shortcuts (Notepad,
      Calculator, uninstallers)
- [ ] Tiles use the warm-near-black palette with a single accent on
      focus

**How to test:** scroll the Home grid; spot-check 3–5 random tiles for
art and titles.

**Expected:** no obvious junk entries; missing art falls back to a
typographic placeholder, not a broken-image icon.

**On failure:** verify the `is_game` filter in the Rust side matches
the frontend filter; check the RAWG image cache at
`%APPDATA%\pixiis\images\`.

---

## 7. Library page

- [ ] Navigate to `/library` (top-nav link or controller)
- [ ] Filter chips (Steam / Xbox / Epic / Favorites / All) toggle the grid
- [ ] Search input filters in real time (debounced)
- [ ] Empty filters render an empty state, not a stack trace

**How to test:** click each chip, then type a substring from a known
game name into the search box.

**Expected:** filters and search compose (chip + search both apply).

**On failure:** inspect `src/pages/Library.tsx` and the
`LibraryContext` filter logic.

---

## 8. Game Detail

- [ ] Click a Steam game tile — navigates to `/game/<id>`
- [ ] Cover art / hero image renders
- [ ] Metadata panel (title, year, genres, rating) populates
- [ ] **▶ PLAY** button is the only accent-colored element on the page
- [ ] Back button (or B on a controller) returns to the previous page

**How to test:** click any Steam tile from Home.

**Expected:** detail page within < 200 ms; metadata appears (RAWG may
fill in async — that's fine, no spinner left dangling).

**On failure:** check the route in `App.tsx` and the `get_game_detail`
invoke handler.

---

## 9. Game launch

- [ ] On the detail page, click **▶ PLAY**
- [ ] The relevant launcher opens (Steam client for Steam games,
      Microsoft Store / Xbox app for UWP, etc.)
- [ ] The game itself starts (or the launcher shows it ready to play)

**How to test:** pick an installed Steam game with a small footprint;
click PLAY; wait for the launcher.

**Expected:** Steam URL handler `steam://rungameid/<appid>` resolves;
no UAC prompt; no error toast.

**On failure:** copy the launch command from `scan_debug.log` and run
it manually in PowerShell to isolate Pixiis vs. the launcher.

---

## 10. Favorites

- [ ] Heart icon on a tile / detail page toggles
- [ ] Favorited games sort first on Home (or appear under the Favorites
      filter on Library)
- [ ] Restart the app — the favorite state is preserved

**How to test:** favorite three games, restart, confirm hearts are still
filled.

**Expected:** `%APPDATA%\pixiis\library_overlay.json` contains the
favorited IDs; UI reflects them on next launch.

**On failure:** inspect `library_overlay.json` for the IDs; check the
overlay-merge step in the library subsystem.

---

## 11. Settings persistence

- [ ] Change a setting (e.g. flip autostart, change scan interval)
- [ ] Click **Apply** / **Save**
- [ ] Quit (tray → Quit) and relaunch
- [ ] The changed value is still there

**How to test:** flip the autostart toggle; restart; confirm the toggle
state matches.

**Expected:** `%APPDATA%\pixiis\config.toml` has the new value; UI
reads it on mount.

**On failure:** open `config.toml` and confirm the write happened;
check the Settings page mount-time read.

---

## 12. Voice (skip if model not bundled)

- [ ] Settings → Voice section is visible
- [ ] **Test voice** button is enabled (model loaded)
- [ ] Hold A on a controller (or the configured trigger), speak a short
      phrase, release
- [ ] Partial transcription appears in the search bar within ~500 ms
- [ ] Final transcription replaces the partial

**How to test:** with a working mic, hold the voice trigger and say
"red dead redemption."

**Expected:** the search bar shows progressive text; final text is
non-empty; library filters as you speak.

**On failure:** check `%APPDATA%\pixiis\models\whisper\` for the
`.bin` file; confirm mic permissions; tail the dev console for VAD /
transcriber errors.

---

## 13. Controller

- [ ] D-pad (or left stick) moves focus tile-by-tile on the Home grid
- [ ] Focus ring is visible on the focused tile
- [ ] **A** activates the focused tile (navigate to detail / launch
      from detail)
- [ ] **Y** toggles favorite on the focused tile
- [ ] **B** goes back / cancels

**How to test:** plug in an Xbox controller; navigate the Home grid;
press A on a tile; press Y on a tile; press B on the detail page.

**Expected:** every input has a visible response; no double-fires; no
ghost focus.

**On failure:** check `useController` / `useSpatialNav` hooks; confirm
gilrs sees the device (Settings → Controller test).

---

## 14. Quick Resume

- [ ] Press the Xbox / Guide button (or the configured Start trigger)
- [ ] Quick Resume overlay appears showing the **last 5 played** games
- [ ] Pressing **A** on a card launches that game
- [ ] Pressing **B** dismisses the overlay

**How to test:** play three games briefly to populate history; open
Quick Resume; launch from it.

**Expected:** overlay covers the current screen, doesn't navigate
away; dismiss restores the previous page.

**On failure:** check the playtime cache in `library_overlay.json`
and the Quick Resume overlay component.

---

## 15. System tray

- [ ] Click the window close button — the window hides, tray icon
      stays
- [ ] Right-click the tray icon — menu shows **Open / Scan / Quit**
- [ ] **Open** restores the window
- [ ] **Scan** triggers a library scan (visible in `scan_debug.log`)
- [ ] **Quit** terminates the process (no `pixiis.exe` left in Task
      Manager)
- [ ] Double-click the tray icon restores the window

**How to test:** close the window; interact with each tray menu item
in turn; finish with Quit.

**Expected:** single-instance enforcement holds — relaunching while
the tray icon is present re-opens the existing window, doesn't spawn
a second process.

**On failure:** check the tray plugin wiring in `src-tauri/src/lib.rs`
and the single-instance plugin config.

---

## 16. File Manager

- [ ] Navigate to `/files`
- [ ] Add a manual entry (title, executable path, optional cover art
      path)
- [ ] Save
- [ ] Return to Library / Home — the manual entry appears in the grid
- [ ] Restart — it's still there

**How to test:** add an entry pointing at any installed `.exe` (e.g.
`C:\Windows\System32\notepad.exe` for the smoke purpose) with a
distinctive title like "Smoke Test Entry."

**Expected:** entry shows up in the manual provider section of the
next scan; persists across restart via `config.toml`'s
`[library.manual]`.

**On failure:** open `config.toml` and confirm the entry was written
under `[library.manual]`; check the manual provider in the scan log.

---

## Done

If every box is ticked: ship it. If any failed and you couldn't
recover: file a bug with the failing section number, the
`scan_debug.log` snippet (if relevant), and a screenshot.
