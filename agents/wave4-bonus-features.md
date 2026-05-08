# Wave 4 — Big Picture Bonus Features

Branch: `feat/big-picture-polish`
Base SHA at start: `fa8bb7a`

## Shipped (6)

### A. Quick Search modal — universal X / Ctrl+K
- New `<QuickSearchProvider>` mounted at the app root
  (`src/components/QuickSearch.tsx`).
- Gamepad **X** opens it from any page; **Ctrl+K** / **Cmd+K** is the
  keyboard equivalent. Esc / B closes.
- Live filter against game names with a 3-tier score (prefix > word
  start > substring). Up to 12 results shown, recently played first
  for the empty-query state.
- D-pad up/down navigates, A launches, Y opens the detail page.
- Editorial styling: top-anchored panel, large serif input, mono key
  hints in the footer. No glass / no springs.

### B. Time + weather greeting on Home
- New `<HomeGreeting>` component
  (`src/components/HomeGreeting.tsx`) reads time locally and fetches
  current weather from Open-Meteo (free, no key needed) when
  configured. Updates exactly on the minute boundary.
- Three lines: small-caps salutation (`GOOD EVENING,`), serif name
  (`fwachira`), monospace time + tracked condition
  (`18:42 · 14° CLOUDY`). Small-caps tracked label, serif for the
  user's name, monospace for the temp — exactly the brief.
- Disabled by default for weather (the user opts in by entering
  coordinates in Settings → About). Toggle and lat/lon fields wire
  through the new `[ui.home]` config block.

### C. Recently Added rail on Home
- Carousel between Continue Playing and the main grid. Reads the
  best-effort timestamp from `metadata.added_at` / `mtime` /
  `modified` / `created_at`, falling back to `last_played`.
- Rail only renders when ≥3 entries have a real timestamp signal;
  otherwise it skips entirely (per-spec — no fake data).
- Excludes any game already in Continue Playing so the rails never
  duplicate cover art.

### D. System power controls
- Three new Tauri commands in
  `src-tauri/src/commands/system.rs`: `system_sleep`, `system_lock`,
  `system_restart`. Cross-platform: Windows shells out to
  `rundll32` / `shutdown`; other OSes return a clean error.
- Wired through new bridge functions (`systemSleep`, `systemLock`,
  `systemRestart`) into a "System power" field in
  Settings → About. Restart prompts a confirm dialog (`ask`) before
  firing.
- Capability: added `dialog:allow-ask` to the default capability
  for the confirmation dialog; the system commands themselves are
  custom invokes so no shell allow-list is needed.

### G. Surprise Me button on Home
- "Surprise me" pill in the Home toolbar. Picks a random installed
  game (falling back to all visible games if none installed) and
  routes to the detail page with a toast — never auto-launches, so
  the user still gets to confirm via ▶ PLAY.
- Toggle in Settings → About; hides the pill entirely when disabled
  or when the filtered list is empty.

### H. Keyboard shortcuts cheat sheet — F1
- New `<ShortcutsCheatsProvider>` mounted at the app root
  (`src/components/ShortcutsCheatSheet.tsx`).
- **F1** anywhere opens a magazine-style modal with two columns:
  Keyboard and Gamepad. Each row: key (mono) / action (body) /
  context (tracked small-caps).
- Esc / B closes. The shortcut map is a static array so additions
  in other features stay in one place.

### Settings — Library export (bonus, scope from feature I)
- Added an "Export library" button in Settings → About. Uses the
  Tauri save dialog and writes a JSON snapshot
  (`{ exported_at, version, count, games }`) via
  `@tauri-apps/plugin-fs`'s `writeTextFile`.

## Supporting work

### `UiPrefsContext`
- New `src/api/UiPrefsContext.tsx` reads `[ui.home]` from
  `config.toml` once on mount and re-reads on a custom
  `pixiis://ui-prefs:changed` event. Settings's `onApply` dispatches
  it after a successful save so HomePage updates without a remount.
- All four discoverable Home features (greeting, recently-added,
  surprise-me, weather) are toggleable from one Settings panel — per
  the brief's "each feature has a Settings toggle" rule.

### Settings — new `[ui.home]` block
- `greeting`, `recently_added`, `surprise_me`, `weather`,
  `weather_latitude`, `weather_longitude`, `display_name`. Lat/lon
  edited as text fields, parsed to numbers when read by the context
  (the greeting only fires the weather fetch when both parse).

### Capabilities
- `src-tauri/capabilities/default.json` added `dialog:allow-ask`
  for the Restart confirmation. The `shell:allow-execute` line is
  *not* needed because `system_*` are custom Tauri commands
  (auto-allowed via `invoke_handler`).

## Deferred

- **E. Better empty Home — Explore CTA**: shipped a smaller variant
  (the "Explore your library" callout when the library has games but
  Continue Playing is empty), wired to a smooth scroll + first-tile
  focus. Not flagged with its own toggle since it replaces a worse
  empty state — not a discoverable feature on its own.
- **F. Genre filter chips on Library**: deferred. The `metadata.genres`
  field isn't reliably populated yet (only when RAWG metadata has
  been fetched). The brief required ≥5 entries with genres before
  the chip row renders, but on a typical first-launch library that
  threshold isn't reached without a manual RAWG sweep — the feature
  would silently never appear and feel broken. Park it until either
  RAWG bulk-prefetch lands or the chips can also key off
  source-derived genres.
- **I. Export library as a file**: shipped as part of the Settings
  About panel; called out separately above.
- **J. Auto-pause-music**: deferred. Requires foreground-audio
  detection (per-process audio sessions on Windows) which is non-
  trivial in Rust without `winrt` / `cpal`-WASAPI plumbing far
  beyond what this session could deliver well. Punted per the brief.

## Acceptance

- 6 features landed (A, B, C, D, G, H) plus a chunk of E and a
  trimmed-down I.
- `npx tsc -b --noEmit` is clean as of the final commit.
- This document records both shipped and deferred features.

## Files

### Added
- `src/components/QuickSearch.tsx` + `.css`
- `src/components/HomeGreeting.tsx` + `.css`
- `src/components/ShortcutsCheatSheet.tsx` + `.css`
- `src/api/UiPrefsContext.tsx`
- `src-tauri/src/commands/system.rs`
- `agents/wave4-bonus-features.md` (this file)

### Edited
- `src/App.tsx` — mount new providers + UiPrefsProvider.
- `src/api/bridge.ts` — `systemSleep` / `systemLock` /
  `systemRestart`.
- `src/pages/HomePage.tsx` — greeting / recently-added /
  surprise-me / Explore CTA.
- `src/pages/HomePage.css` — surprise pill + CTA styles.
- `src/pages/SettingsPage.tsx` + `.css` — toggles, weather coords,
  power buttons, library export.
- `src-tauri/src/commands/mod.rs` — register `system` module.
- `src-tauri/src/lib.rs` — wire `system_*` commands.
- `src-tauri/capabilities/default.json` — `dialog:allow-ask`.

## Screenshots

Not captured — Linux dev environment, no Windows runtime here.
Suggested capture points for QA:
- `/screens/wave4-quick-search.png` — Ctrl+K modal over Library.
- `/screens/wave4-greeting.png` — Home top-left greeting.
- `/screens/wave4-recently-added.png` — three rails stacked.
- `/screens/wave4-cheatsheet.png` — F1 modal centred.
- `/screens/wave4-power.png` — Settings → About power row.
