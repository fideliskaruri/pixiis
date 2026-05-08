# Wave 3 — Settings Apply + Onboarding first-launch audit

Branch: `wave3/settings-onboarding`
Worktree: `agent-a479f9dee93399953`

Two flows audited end-to-end. Settings was **BROKEN** (no-op stubs on
the Rust side) and is now **FIXED**. Onboarding was already **OK** end
to end and is left unchanged.

## Settings persistence — FIXED

**Symptom**

Every Apply on the Settings page round-tripped a fully-formed JSON
patch through `invoke('config_set', { patch })`, but the Rust handler
was a stub that returned `Ok(())` without writing a single byte. A
matching `config_get` returned an empty map, so the page also never
actually loaded the persisted state on mount — it always showed
`DEFAULTS`. Reload, relaunch, or even page-revisit lost every change.

**Root cause** — `src-tauri/src/commands/config.rs`

Both commands were placeholders left over from Phase 1A scaffolding:

```rust
// before
#[tauri::command]
pub async fn config_get() -> AppResult<Map<String, Value>> {
    Ok(Map::new())
}

#[tauri::command]
pub async fn config_set(_patch: Map<String, Value>) -> AppResult<()> {
    Ok(())
}
```

There is no `core/config.rs` module — the only place a real config
loader exists is `src-tauri/src/lib.rs::load_default_macros`, which
parses `resources/default_config.toml` once at startup just to seed
the controller-macro engine. Nothing else reads or writes the user's
`%APPDATA%/pixiis/config.toml`.

**Audit of the rest of the path**

Frontend (no bugs):

- `src/pages/SettingsPage.tsx:235-258` — `onApply` invokes
  `config_set` with `{ patch: toPatch(state) }`. Arg name matches the
  Rust signature. Patch shape is the standard nested TOML structure
  (`library.providers`, `voice.model`, `controller.deadzone`,
  `services.rawg.api_key`, `daemon.autostart`, …) — all keys line up
  with the section names in `resources/default_config.toml`.
- `src/pages/SettingsPage.tsx:208-225` — load on mount calls
  `config_get` and runs the result through `fromConfig`, which uses
  `readDotted` to pluck nested keys. Wire is correct; only the backend
  was broken.
- `src/api/bridge.ts:163-172` — `getConfig` / `saveConfig` thin
  wrappers; argument is named `patch` to match the Rust handler.

Backend (one fix):

- `src-tauri/src/commands/config.rs` — rewrote `config_get`,
  `config_set`, `config_reset` to actually round-trip the user's
  `%APPDATA%/pixiis/config.toml` through `toml_edit::Document`. Key
  properties:
  - **Comments + ordering preserved.** `toml_edit` keeps the original
    layout, so a user who hand-edited their `config.toml` sees their
    comments survive every Apply. (Standard `toml::to_string` round-
    trip would have lost them.)
  - **Nested keys merge, not replace.** `merge_into_table` recurses
    into JSON object values, so a patch that touches
    `services.rawg.api_key` does NOT clobber sibling
    `services.youtube.api_key`. Verified by the
    `merge_handles_deep_nesting` unit test.
  - **Arrays replace whole.** `library.providers = ["steam", "xbox"]`
    overwrites the previous list, which matches the UI semantics
    (checkboxes are absolute, not additive).
  - **Atomic write.** Writes to `config.toml.tmp` then renames, so a
    crash mid-write never leaves a half-written file.
  - **Default-config fallback.** When `%APPDATA%/pixiis/config.toml`
    doesn't exist yet, the loader falls back to
    `resources/default_config.toml` (release bundle or dev path)
    before a final fallback to an empty document — so first-Apply
    inherits the bundled comments + defaults.

- `src-tauri/Cargo.toml` — added `toml_edit = "0.20"` (matches the
  version `toml 0.8.2` already pulls in transitively).

**Verification**

Unit tests in `src-tauri/src/commands/config.rs::tests`:

- `merge_preserves_sibling_keys` — patching `library.providers` keeps
  `library.scan_interval_minutes` and its `# how often the background
  sweep runs` comment.
- `merge_handles_deep_nesting` — patching `services.rawg.api_key`
  doesn't touch `services.youtube.api_key`.
- `merge_creates_missing_tables` — patching into an empty document
  works (first-launch path).
- `json_view_round_trips_scalars` — strings, numbers, arrays come back
  the way the SettingsPage expects.

Cross-checked the same logic in an isolated cargo crate (Linux WSL
can't compile the full Tauri tree without `libdbus-1-dev`) — all four
tests pass green.

Section-by-section round-trip readiness:

- **Library** — `library.providers` (array of strings),
  `library.scan_interval_minutes` (int). Round-trips.
- **Voice** — `voice.model`, `voice.device`, `voice.mic_device_id`,
  `voice.energy_threshold`. Note: `default_config.toml` ships
  `voice.live_model` / `voice.final_model`, but the SettingsPage uses
  `voice.model`. New keys are written alongside the existing ones
  rather than replacing them; this is a soft schema mismatch — the
  Settings UI's chosen model survives reloads, the legacy live/final
  pair just stays as-is. Out of scope for this audit but flagged.
- **Controller** — `controller.deadzone`, `controller.hold_threshold_ms`,
  `controller.vibration_enabled`, `controller.voice_trigger`. Round-
  trips.
- **Services** — `services.rawg.api_key`, `services.youtube.api_key`.
  Twitch tokens come from a separate OAuth flow; not in the Apply
  patch.
- **About** — `daemon.autostart`. Round-trips into the config.
  `app_set_autostart` is still a stub that doesn't register the OS-
  level launch entry (documented in the file as Phase 1A work) — but
  user intent persists.

**Files touched**

- `src-tauri/src/commands/config.rs` — full rewrite of get / set /
  reset, plus four unit tests.
- `src-tauri/Cargo.toml` — added `toml_edit` direct dep.

## Onboarding first-launch — OK

**Audit**

- `src/pages/OnboardingPage.tsx:38-52` — `finish(markComplete)` calls
  `setOnboarded(true)` regardless of the markComplete flag (skip and
  finish both flip the marker), then `navigate('/', { replace: true
  })`. The catch is silent-but-permissive: a marker-write failure
  still navigates, so the user is never trapped.

- `src/App.tsx:32-60` — `useEffect` runs **once on mount** (empty
  dep array, with the eslint-disable comment explaining why). It
  reads the marker via `getOnboarded()`, redirects to `/onboarding`
  iff missing, and sets `checkedOnboarded` in `.finally()`.
  Routes only mount once `checkedOnboarded` flips, so HomePage never
  flashes before the redirect lands.
  - The redirect is gated on `location.pathname !== '/onboarding'`,
    so even a user who deep-links to `/onboarding` won't be bounced.
  - Catch swallows errors — if the IPC fails the user gets to the
    main app, which is the right safety valve (better than trapping
    them in a loop they can't exit).

- `src-tauri/src/commands/config.rs:44-76` —
  - `app_get_onboarded` checks for `<app_data_dir>/.onboarded`.
  - `app_set_onboarded(true)` creates the parent dir, writes a single
    byte to `.onboarded`.
  - `app_set_onboarded(false)` removes the file.
  - On Windows `app_data_dir` resolves to
    `%APPDATA%/pixiis/`, so the marker is a sibling of the user's
    `config.toml` — **separate file, survives a config reset**, which
    is the desired behaviour (resetting settings shouldn't re-trigger
    onboarding).

**Race / re-bounce check**

The `useEffect` is mount-only. After onboarding completes, the user
navigates to `/`, the App component does NOT re-run the marker check,
so there's no path where the user can be bounced back to
`/onboarding` mid-session.

The first render of `AppContent` shows an empty `<main>` (no Routes)
until `checkedOnboarded` flips, so there's no flash of HomePage
before the redirect resolves. The OnboardingPage path is mounted via
the early-return on `location.pathname === '/onboarding'`, so once
the navigate lands the OnboardingPage renders immediately on the next
tick.

**Verdict** — no fix needed. The flow is correct and race-free.

## Summary

| Flow                            | Status       |
| ------------------------------- | ------------ |
| Settings → Apply persistence    | **FIXED**    |
| Onboarding first-launch trigger | **OK**       |

Bugs found: 1 (Settings persistence — `config_get` / `config_set`
were stubs).
Bugs fixed: 1.
Outstanding: `app_set_autostart` is still a Phase 1A stub
(intentional, doesn't block the audit). `voice.live_model` /
`voice.final_model` vs `voice.model` is a soft schema mismatch
(out of scope).
