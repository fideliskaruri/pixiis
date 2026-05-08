# Wave 3 final report — 2026-05-08

You were away for ~2 hours. Here's what changed and what you need to do.

## Snapshot

- **Branch:** `wave1/integration` and `master` both at `533c9ad`
- **Tag:** `v0.2.0` at HEAD
- **TS compile:** clean (`npx tsc -b --noEmit` → 0)
- **Branches:** 2 (master + integration). All 24 wave1/wave2/wave3 feature branches deleted.
- **Worktrees:** 1 (just main). All 3 stale agent worktrees removed.
- **Working tree:** clean.

## What was bugged when you left

You reported two:

1. **"Library — coming soon" still showed.** Diagnosis: stale build. The wave3 merge that replaced the placeholder with `<LibraryPage />` was on disk but your `pixiis.exe` was from before the merge.

2. **"Games still don't scan on load."** Same root cause — the auto-scan-on-empty logic was on disk but not in your binary.

Both are fixed by rebuilding from `533c9ad`. But while I was on it, I also caught and fixed real bugs that would've bitten you next:

## Real bugs caught and fixed (audit pass)

### Backend
- **Steam multi-library scanner was silently truncating** — `splitn(2, '"')` instead of `splitn(3, '"')` in `parse_library_folders`. Anyone with games on a second drive was only seeing their primary library. Your "70 games" was probably understated. (`src-tauri/src/library/steam.rs`)
- `lib.rs` default-config fallback path duplicated; now correctly tries `../resources/default_config.toml` then the project-root copy.

### Frontend reliability
- **Auto-scan retry-on-failure**: previously if the first auto-scan rejected (transient panic, network glitch), the latch flipped permanently → empty Home until manual Settings → Scan Now. Now retries 2× with 3-second backoff.
- **`Onboarding` race against `LibraryProvider`** — both were firing scans simultaneously and the reports clobbered each other. Provider now skips when `location.pathname === '/onboarding'`.
- **B-button triple-listener conflict** — pressing B in QuickResume / VirtualKeyboard / Lightbox closed the modal AND fired `window.history.back()` simultaneously. Now skipped when any `[aria-modal="true"]` is in the DOM. (`useSpatialNav.ts`)
- **VirtualKeyboard never closed on input blur** — fixed.
- **`voiceStop()` typed as `string` but Rust returns `TranscriptionEvent`** — would've rendered `[object Object]` in any caller. Fixed with defensive string-fallback for stub builds.
- **Onboarding `setTimeout` leak on unmount** — fixed.
- **Removed `console.log('[scan]', …)` debug cruft.**

### UX completeness
- **HomePage no-match empty state** now offers "Clear search" instead of leaving you stuck.
- **LibraryPage empty/filter-wedged states** branched with "Clear filters" recovery.
- **Settings retry button** — first `config_get` failure no longer leaves the form blank forever; now has a Retry that re-runs the load.
- **FileManagerPage success/error toasts** on save/delete; cancellation-tolerant file picker (Cancel doesn't toast as error).

### Design drift
- **VoiceOverlay listening dot** was using `var(--accent)` — violated single-accent rule. Now `var(--text)`.
- **Toast success border** now uses `color-mix` against `--text` instead of a hard-coded rgba.
- **QuickResume backdrop** now uses `color-mix` against `--bg` instead of hard-coded rgba.

### New: scan progress on Home
When auto-scan fires on first launch, Home now renders a `<ScanProgress>` component (extracted to `src/components/ScanProgress.tsx`) that shows the same per-provider readout as Onboarding:

```
STEAM      ✓  43
XBOX       ⠿  scanning…
EPIC       —  not detected
GOG        ✕  error: …
EA         ·  pending
START MENU ✓  18
```

OnboardingPage was refactored to use the same component (~140 lines of duplicated row/glyph code removed).

## What you need to do when you're back

### 1. Rebuild

```powershell
cd D:\code\python\pixiis
npm run tauri build
```

The new installer at `src-tauri/target/release/bundle/nsis/Pixiis_0.2.0_x64-setup.exe` will have:
- Library page (real)
- Auto-scan on first launch (with retry)
- All overlays restored
- F11 fullscreen
- Steam multi-library scanner that finds games on every drive
- Settings persistence that actually writes to disk

### 2. Walk through `SMOKE.md`

It's at the repo root. 16 sections, checkbox-style. Tells you what to verify, what's expected, and what to do on failure.

### 3. (Optional) Drop the Whisper model for voice search

```powershell
mkdir -Force "$env:APPDATA\pixiis\models\whisper" | Out-Null
curl.exe -L -o "$env:APPDATA\pixiis\models\whisper\ggml-base.en-q5_0.bin" `
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en-q5_0.bin
```

Restart the app. Voice search will go from "voice unavailable" to functional.

### 4. (Optional) Run the perf script

```powershell
.\scripts\perf.ps1
```

Produces `scripts/perf-results.md` with cold start time, scan time, bundle size. Compare against migration plan targets.

## What I did NOT do (intentionally)

- **Did not push to remote.** No upstream is configured for `wave1/integration`, and you didn't authorize a push. To push when you're ready:
  ```bash
  git push -u origin master
  git push --tags
  ```
- **Did not update the README's `your-org` placeholder.** I don't know your real GitHub repo URL.
- **Did not sign the binary.** That requires a real Authenticode certificate I don't have.

## Audit reports

Each audit agent left its findings:

- `agents/wave3-frontend-audit.md` — 9 frontend bugs, all fixed inline
- `agents/wave3-rust-audit.md` — 3 backend issues, all fixed inline (Steam scanner is the big one)
- `agents/wave3-design-audit.md` — 3 drift violations fixed, 2 deferred (design call)
- `agents/wave3-ux-audit.md` — page-by-page state of empty/error handling
- `agents/wave3-settings-onboarding-audit.md` — Settings persistence rewrite + Onboarding marker audit

## Commit log highlights (since you left)

```
533c9ad docs: archive remaining wave3 agent briefs
122fd0c merge: ux-states into wave1/integration
f0e6473 merge: auto-scan-retry into wave1/integration
4ac26a3 merge: frontend-hunt into wave1/integration
3ed7b81 merge: design-audit into wave1/integration
1b4e0bf merge: rust-audit into wave1/integration
... (Wave 3 page implementation merges from earlier in the day)
```

## TL;DR

Rebuild → run SMOKE.md → drop Whisper model if you want voice → ship it. The codebase is in a substantially better state than when you left.
