# Wave 2 Pane 6 — Onboarding page (editorial)

**Branch:** `wave2/onboarding-page`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-onboarding/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

Build a new **Onboarding** page — multi-step, large serif headlines, generous whitespace. Shows on first launch (no `.onboarded` marker), guides through scan + voice + controller test.

## Reference

- Python original: `src/pixiis/ui/pages/onboarding_page.py`
- Tokens: `src/styles/tokens.css`, `src/styles/PALETTE.md`
- Existing editorial pages: `src/pages/HomePage.tsx`, `GameDetailPage.tsx`
- Commands: `library_scan`, `voice_get_devices`, `voice_start`, `controller_get_state`
- Marker file: writes `%APPDATA%/pixiis/.onboarded` after completion (replaces Python's `cache_dir() / .onboarded` path)

## Deliverables

1. **`src/pages/OnboardingPage.tsx`** — route `/onboarding`:
   - Single-column, max-width ~720 px, centered
   - 5 steps with cross-fade between each (200 ms):
     1. **Welcome** — "Pixiis" in display serif, subtitle "Your games, one launcher." Single button "Begin".
     2. **Library scan** — fires `library_scan`, shows live store-by-store progress via `library:scan:progress` events. One row per provider: `STEAM ✓ 47 games`, `XBOX ⠿ scanning`, `EPIC ✗ not detected`.
     3. **Voice mic test** — picks default mic, shows level meter (use Web Audio API `AnalyserNode` against the mic stream OR poll partial transcription events — pick whichever is simpler). User holds the on-screen "Speak" button, sees their words.
     4. **Controller test** — shows "Press any button" prompt, lights up matching glyph as inputs come in (uses existing `useController.ts` hook). User confirms with "Looks good".
     5. **Done** — "You're ready." + "Open Pixiis" button → writes the `.onboarded` marker via a new tiny invoke command (or use `config_set` with a `meta.onboarded = true` key) and navigates to `/`.
2. **`src/pages/OnboardingPage.css`** — editorial, generous whitespace (clamp(2rem, 8vw, 6rem) padding), no glass.
3. **Step indicator:** small-caps tracked text bottom-center: `STEP 1 / 5` etc.
4. **Skip option:** small ghost link top-right "Skip setup" — sets the marker and navigates home.
5. **Invoke command for the marker:** add `app_set_onboarded(value: bool)` in `src-tauri/src/commands/config.rs` if not already there. (`config_set` with patch is fine too — coordinate with what exists.)
6. **Route registration** in `App.tsx`.
7. **First-launch redirect:** in `App.tsx` or a top-level effect, check the onboarded flag on mount; if false, navigate to `/onboarding`.

## Acceptance criteria

- First launch → `/onboarding` automatically
- Subsequent launches → `/` (home)
- "Skip setup" works and sets the marker
- Each step's interactive test reflects real data (no stubs in the final render — though you can use mocks during dev)
- Editorial language only

## Out of scope

- Theme picker during onboarding
- Account creation / sign-in
- Tutorial overlay on the dashboard after onboarding (future)

## Reporting

Append to `agents/STATUS.md`. Commit to `wave2/onboarding-page`.
