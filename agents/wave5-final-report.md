# Wave 5 final report — 2026-05-09

You went to watch a movie. Here's what happened.

## Snapshot

- **Branch:** `master` and `wave1/integration` both at `f6a0bbc`
- **Tag:** `v0.2.2`
- **Pushed:** all of master, wave1/integration, v0.2.2 → `git@github.com:fideliskaruri/pixiis.git`
- **TS compile:** clean
- **Worktrees:** 1. All agent worktrees cleaned up.

## Approach this time

You said the UX was shitty and "you can search online and read docs for as long as you want." Per your instruction, **UX research came first** — a single research/design agent spent ~15 minutes reading Xbox docs, Steam Big Picture community threads, Playnite Fullscreen issues, Plex/tvOS HIGs, and the current Pixiis source. Output: `agents/wave5-ux-research.md` (494 lines). Personas, findings with cited sources, page-by-page diagnosis with file:line refs, top-10 ranked recommendations, full implementation contracts.

Only after that did I spawn 5 implementation agents in parallel against the contracts.

## What you complained about — all addressed

### 1. "Voice model not available" persisted

**Root causes (3 stacked):**
- Default `voice_model` was `'large-v3'` while Pixiis bundles `ggml-base.en-q5_1.bin`. Default flipped to `'base'`.
- Tauri 2's NSIS bundler rewrites `bundle.resources` entries containing `..` to `_up_/resources/...` under `$INSTDIR`. The Rust loader was probing the wrong path. Now probes `_up_/resources/models/...` first, with diagnostic `eprintln!` traces on every fallback.
- Added a download fallback: if the model is genuinely missing, Settings → Voice now has a "Download voice model" button with MB/percent progress that streams from HuggingFace into `%APPDATA%/pixiis/models/whisper/`.

### 2. RT trigger and overlay didn't show

`controller.voice_trigger` was config-only — no runtime consumer. Fixed:
- New `src/hooks/useVoiceTrigger.ts` polls Standard Gamepad at ~60 Hz
- Reads the configured trigger (rt/lt/hold_y/hold_x), fires `voiceStart()` / `voiceStop()` on rising/falling edge
- Mounted globally in App.tsx
- VoiceOverlay slides in from bottom-right (160 ms ease-out) with state labels per the UX research § 5.4: `LISTENING` → `STILL LISTENING…` (after 1.5 s no partial) → `TRANSCRIBING` → result for 5 s
- Final transcript dispatches into the input that was focused when recording started; if no input was focused, opens QuickSearch with the text pre-filled
- Error states are clean: `MODEL NOT INSTALLED · Open Settings` and `MICROPHONE DENIED · check Windows privacy` instead of raw error toasts

### 3. Settings page navigation was shit

Per UX research § 3.1 + 5.1:
- First form control auto-focused on section change (was: re-focused the LIBRARY tab every time)
- LB/RB inside Settings now cycle **sections** (LIBRARY → VOICE → CONTROLLER → SERVICES → ABOUT), not top-level pages — overrides `useBumperNav` only on `/settings`
- Y button presses Apply from anywhere
- B from a form control returns focus to the section tab; B on the tab navigates back
- Section nav 240 px wide; Field rows 96 px tall; sliders ≥ 320 px wide / 24 px thumbs; Apply 64 px tall
- 4 px accent focus rings (was 2 px); 6 px offset (was 4 px)

### 4. On-screen keyboard activation was broken / "press A bring it up"

Per § 5.3:
- Today's flow already auto-opens on input focus when gamepad activity was recent — that part works
- Added: pressing A on a focused input where the keyboard was previously dismissed reopens it. New `reopen()` method on `VirtualKeyboardProvider`.
- Added: action footer entries when an input is focused make the flow discoverable.

### 5. Every UI area must be controller-accessible

The biggest UX gap. Five additional controller bindings shipped:
- **Sliders:** D-pad left/right adjust value (was: ignored). Used by deadzone, hold ms, energy threshold, UI scale.
- **`<select>` dropdowns:** A press calls `showPicker?.()` (Chromium 102+) with a synthetic mousedown fallback.
- **GameTile Y:** gamepad Y now toggles favorite on the focused tile (was: keyboard 'y' fallback only worked).
- **`data-hold-to-activate`:** press A to dispatch synthetic `pointerdown`, release A to dispatch `pointerup`. Used by Settings "Hold to test" voice button and Onboarding "Hold to speak."
- **SearchBar mic button:** click toggles voice recording (was: no handler).

### 6. "RT shortcut and overlay don't even show up"

This was the #2 issue above — fixed in `useVoiceTrigger`.

### 7. Discoverability — every UI area, what does each button do?

**Universal action footer.** Persistent fixed-position bar at the bottom of every page showing the current button → action map, Steam-Big-Picture style. Cited by Xbox docs, Xbox Accessibility Guideline 112, Steam Big Picture, Playnite as **the** most-cited TV-app affordance. Pixiis had zero of it before.

11 surfaces register their action set:
- 6 pages (Home, Library, GameDetail, Settings, Onboarding, FileManager)
- 5 modals (QuickResume, QuickSearch, VirtualKeyboard, ShortcutsCheatSheet, Lightbox)

Each page/modal calls `useActionFooter([...])` on mount, clears on unmount → falls back to defaults. Modals override and restore. Glyphs use the universal Xbox palette: A green, B red, X blue, Y yellow.

Bonus: switched QuickSearch trigger from X to Y to match the Xbox convention (Y = Search across all consoles, per docs cited in UX research § 2.1).

### 8. TV-distance readability

Type scale grew in fullscreen mode:
- body 16 → 18 px, label 12 → 14 px, caption 14 → 16 px
- display max bumped 96 → 112 px
- Focus ring 2 → 4 px width, 4 → 6 px offset
- Tile width clamp(280, 18vw, 360) — was ~250 px
- Tile focus scale 1.04 → 1.06 + drop shadow `0 12px 32px var(--accent)/30%`
- Grid gap 16 → 24 px

### 9. Grid traversal was wonky

`useSpatialNav` was purely geometric — could skip rows when widths varied. Now uses `data-grid-row` (computed via ResizeObserver on the grid container) to prefer row-±1 candidates over row-±2 in vertical traversal. Plus 2-D grids no longer wrap edges (per Xbox Accessibility Guideline 112).

## What actually shipped (file count)

**24 files modified, 7 files added.** Highlights:

- New: `src/hooks/useVoiceTrigger.ts`, `src/components/ActionFooter.tsx`+`.css`, `src/api/ActionFooterContext.tsx`, `agents/wave5-ux-research.md`, `agents/wave5-final-report.md`
- Heavy edits: `src/hooks/useSpatialNav.ts` (3 agents touched it — slider intercept, sectioned-grid mode, row-aware), `src/pages/SettingsPage.tsx` (4 agents touched it), `src/components/VirtualKeyboard.tsx`, `src/components/SearchBar.tsx`, `src/components/VoiceOverlay.tsx`, `src/components/GameTile.tsx`+`.css`, `src/styles/tokens.css`, `src-tauri/src/voice/model.rs`
- New Rust commands: `voice_status`, `voice_download_model`

## What I deferred

- **Custom `<Select>` component** — used `showPicker()` fallback instead. Native dropdown popup is OS-styled but navigable. Worth replacing if the OS popup looks bad on TV.
- **Idle attract mode** (UX research § 6) — out of scope for this wave
- **Information architecture redesign** (Top 10 #10 — collapsing Home/Library) — design call, deferred
- **First-launch button-tour overlay** (Top 10 #9) — deferred; the action footer covers most of the same ground passively

## What still needs your hardware

Everything in this wave was built against `wave5-ux-research.md` contracts. WSL can't run the Tauri runtime or test on a controller. Specific items that need your eyes:

1. **Voice flow end-to-end:** install fresh, hold RT, speak — does the overlay appear, does transcription land?
2. **Settings layout:** 4 px focus rings readable from couch? Section LB/RB cycling feels right?
3. **Action footer:** glyphs render at correct sizes, colors look right against the editorial palette?
4. **Tile grid:** 280 px tiles at 1080p look big enough?
5. **Spatial nav row-awareness:** D-pad down from row 1 lands in row 2, not row 3?

If anything's off, paste what you see and which page. Sub-fixes are 5 min each.

## Build it

```powershell
cd D:\code\python\pixiis
git pull
npm install
npm run tauri build
```

Output: `src-tauri/target/release/bundle/nsis/Pixiis_0.2.2_x64-setup.exe`. Walk SMOKE.md after install.

## Commit log (since v0.2.1 push)

```
f6a0bbc docs: archive wave5 UX research + design recommendations
a0c43eb merge: controller-bindings into wave1/integration
<merge: settings-redesign>
<merge: voice-e2e>
<merge: tv-tiles>
<merge: action-footer>
+ 5 feature commits underneath
```

11 commits since the prior push.
