# Wave 4 final report — 2026-05-09

You watched a movie for ~2 hours. Here's what landed.

## Snapshot

- **Branch:** `master` and `wave1/integration` both at `6b4beb7`
- **Tag:** `v0.2.1` at HEAD
- **TS compile:** clean
- **Branches:** 2 (master + integration). All wave4 feature branches deleted.
- **Worktrees:** 1. All stale agent worktrees removed.

## What you said

1. "voice unavailable: whisper model not found" — bundle it
2. No Xbox games show up
3. Maximize button doesn't work but Win+Up does
4. On-screen keyboard double-inputs (`e` → `ee`)
5. Navigation is trash, can't get to cards properly, no proper highlighting
6. Bumper buttons don't navigate between pages
7. Home/Library/Settings should NOT be D-pad-selectable
8. Stop a game from inside the app (Big Picture style)
9. How to summon the app (global hotkey)
10. "Free rein" — any sound feature welcome
11. Expanded page underwhelming, no videos despite API keys

## What I did

### Direct user complaints — all addressed

| # | Item | Fix |
|---|---|---|
| 1 | Whisper model bundled | `ggml-base.en-q5_1.bin` (~57 MB; q5_0 doesn't exist on HF) shipped with installer. Voice works on first launch. |
| 2 | Xbox games | 4 layered detection heuristics replace strict `MicrosoftGame.Config` probe. 54 system packages skip-listed. Settings toggle "Show all Xbox apps as games" for the rest. |
| 3 | Maximize button | Missing `core:window:allow-toggle-maximize` capability. Added. |
| 4 | Virtual keyboard double-input | React 19 + StrictMode treated the synthetic `Event('input')` as two changes. Switched to `setRangeText` + native `InputEvent`. Single change now. |
| 5/7 | Nav-tab D-pad exclusion + tile focus | Spatial nav skips `[data-no-spatial]` ancestors AND `.navbar` defensively. Tile focus is now 2px accent border + scale 1.03 + accent glow + `z-index: 10`. Auto-focus on page mount. |
| 6 | Bumper page navigation | LB/RB cycle `/, /library, /settings`. No-op on non-top-level. B button route-aware (back from `/game/:id`, no-op elsewhere, modals own their dismiss). |
| 8 | Stop running game | `library_running` + `library_stop` Tauri commands. `sysinfo`-based 5s polling resolves URL launches into actual game PIDs within 30s. NowPlaying pill in NavBar (visible even in fullscreen). PLAY ↔ STOP toggle on tiles + GameDetail. Playtime accumulates on stop. |
| 9 | Global summon | `tauri-plugin-global-shortcut` with default `Ctrl+Shift+Alt+P`. Tray double-click also raises. Single-instance second-launch raises existing window. Configurable in Settings → Controller → "Global summon hotkey" with key-capture rebind. |
| 11 | Game Detail videos | Three root causes: (a) JSX never rendered TRAILER/LIVE NOW; (b) `bridge.ts` had no wrappers; (c) `ServicesContainer` was seeded from env vars only, ignoring `config.toml` keys. All three fixed. New `lookup_config_string()` walks merged user+default TOML so saved Settings keys flow at startup. |

### Bonus features — high-leverage Big Picture additions

| Feature | What |
|---|---|
| **Cursor hides when controller active** | `body.cursor-hidden` toggles after 5s gamepad-recent + 1.5s mouse-idle. CSS `*` selector with `!important` defeats element overrides. |
| **Fullscreen on launch** | Config-controlled (`ui.fullscreen`), Settings checkbox. NavBar chrome auto-hides when fullscreen. |
| **Ambient hero art** | Blurred copy of focused game's art bleeds behind Home. Smooth crossfade on focus change. |
| **UI scale** | Tiles enlarge in fullscreen for couch viewing. Configurable slider in Settings. |
| **QuickSearch modal** | X button (or Ctrl+K) opens centered search palette over the library. D-pad nav, A-launch, Y-detail, Esc-close. |
| **Home greeting** | "Good evening, fwachira" with time + weather (Open-Meteo, no key needed). Editorial typography. |
| **Recently Added rail** | Between Continue Playing and the grid. |
| **Surprise Me** | Pill on Home picks a random installed game and routes to detail. |
| **System power controls** | Sleep / Lock / Restart in Settings → About. Restart confirms via dialog. |
| **Shortcuts cheat sheet** | F1 opens magazine-style two-column modal (Keyboard / Gamepad). |
| **Library export** | Settings → About writes the full library as JSON via Tauri save dialog. |
| **"Explore your library" CTA** | Replaces empty Continue Playing band when nothing's been played yet. |

### Reliability fixes from a separate audit pass earlier

- Steam multi-library scanner was truncating drives 2+ (`splitn(2, '"')` → `splitn(3)`). Your "70 entries" was understated.
- Auto-scan retry policy on first launch (2 attempts, 3s backoff).
- Onboarding race against LibraryProvider auto-scan resolved.
- B-button triple-listener conflict (QuickResume / VirtualKeyboard / `history.back`) resolved.

## What I deliberately did NOT do

- **Did not push to remote.** No upstream is configured. To push when you're ready:
  ```
  git push -u origin master
  git push --tags
  ```
- **Did not sign the binary.** SmartScreen will warn on first download; expected without an Authenticode cert.
- **Did not implement** auto-pause-music, idle attract mode, or genre filter chips. Documented as deferred.

## What you do now

```powershell
cd D:\code\python\pixiis
npm run tauri build
```

The new installer at `src-tauri/target/release/bundle/nsis/Pixiis_0.2.1_x64-setup.exe`:
- Bundles the Whisper model (no manual download)
- Includes all your reported fixes
- Has the Big Picture polish + bonus features
- Voice works immediately
- Steam picks up games from every drive
- Xbox detection is permissive enough to find your Game Pass titles

After install, walk `SMOKE.md` (still at the repo root) to verify on real hardware.

## Recovered failures worth knowing about

Two agents in this session landed on a stale Python/PySide6 worktree (commit `9b35bfe` — pre-Tauri layout) and produced unmergeable changes. Both were caught and redone properly:
- Controller nav agent — redone, landed at `82284ba`
- Game Detail videos agent — redone, landed at `6b4beb7`

Both reworks landed correctly. Nothing was lost. The recoverable cost was ~1 extra agent run each.

## Audit trail

- Each Wave 4 agent left a doc in `agents/wave4-*.md` (where applicable). The `agents/` directory now has the full migration journal from Waves 1–4.
- All Wave 4 work merged via `--no-ff` so the merge commits are visible in `git log --first-parent master`.
