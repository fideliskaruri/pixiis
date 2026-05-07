# Wave 2 Pane 5 — Settings page (editorial)

**Branch:** `wave2/settings-page`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-settings/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Build a new **Settings** page in the editorial language. Section nav on the left, form on the right. Voice section has a live mic test.

## Reference

- Existing pages for style: `src/pages/HomePage.tsx`, `src/pages/GameDetailPage.tsx` (already editorial)
- Tokens: `src/styles/tokens.css`, `src/styles/PALETTE.md`
- Python original (for which controls to expose): `src/pixiis/ui/pages/settings_page.py`
- Tauri commands available: `config_get`, `config_set`, `config_reset`, `voice_get_devices`, `voice_set_device`, `voice_start`, `voice_stop`, `services_oauth_start`, `app_set_autostart`
- Type bindings: `src/api/types/`

## Deliverables

1. **`src/pages/SettingsPage.tsx`** — new component, route `/settings`:
   - Two-column layout (left: section nav, right: form)
   - Sections: **Library**, **Voice**, **Controller**, **Services**, **About**
   - Small-caps tracked label for each section heading
   - Cross-fade transition when section changes (200 ms ease-in-out, no spring)
   - All text in `var(--text)`, dim labels in `var(--text-dim)`
2. **`src/pages/SettingsPage.css`** — editorial layout, no glass, no springs
3. **Library section:**
   - Provider toggles: Steam, Xbox, Epic, GOG, EA, Start Menu, Folder Scanner (checkboxes)
   - Scan interval slider (1–1440 min)
   - "Scan Now" button (calls `library_scan`, shows live progress via `library:scan:progress` events)
4. **Voice section:**
   - Whisper model dropdown (tiny / base / small / medium / large-v3)
   - Compute device dropdown (auto / cuda / cpu) — disabled if no CUDA
   - Mic device dropdown (populated from `voice_get_devices()`)
   - Energy threshold slider
   - **"Test voice" button** — `voice_start` on press-and-hold, live partial events render below as small-caps muted text, final replaces partial. `voice_stop` on release.
   - **"Test TTS" button** — calls `voice_speak("This is the Pixiis voice...")`
5. **Controller section:**
   - Deadzone slider (0–0.5)
   - Hold threshold slider (100–500 ms)
   - Vibration toggle
   - Voice trigger dropdown (RT / LT / Hold Y / Hold X)
   - Connected controller status (live from `controller_get_state`)
6. **Services section:**
   - RAWG API key input
   - YouTube API key input
   - **Twitch OAuth button** — calls `services_oauth_start({provider:"twitch"})`, shows "Connected" / "Not connected" / "Check your browser"
7. **About section:**
   - Version, license, links to GitHub, etc.
   - **Autostart toggle** — calls `app_set_autostart({enabled})`
8. **Persistence:** Apply button saves all changes via `config_set({patch})`. Show "Saved ✓" feedback for 2 s.
9. **Add route** in `src/App.tsx` if not already there.

## Acceptance criteria

- All controls reflect current config on load (`config_get`)
- Apply persists to `%APPDATA%/pixiis/config.toml`
- Voice test panel works end-to-end (you'll need Pane 1's voice integration — that's a soft dep; if Pane 1 hasn't merged, the buttons can show "Pending wave2/voice merge")
- Editorial language only — no glass, no springs, no glow

## Out of scope

- Theme editor — keep it as a future enhancement
- Hotkey customization
- Per-game settings

## Reporting

Append to `agents/STATUS.md`. Commit to `wave2/settings-page`.
