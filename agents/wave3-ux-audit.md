# Wave 3 — UX completeness audit

Branch: worktree-agent-a5457c09fb319aa5e (off wave1/integration @ c4a71bb)
Goal: every page handles loading, empty, and error states gracefully; every
`invoke()` rejection has a recovery surface (toast / retry / inline message).

Legend: `FIXED` = changed in this wave. `WAS-OK` = already correct. `DEFERRED` = noted but out of scope.

---

## src/pages/HomePage.tsx — FIXED (small)

State machine traced:
- `status === 'idle' | 'loading'` and games empty → "One moment / LOADING LIBRARY". WAS-OK.
- `status === 'error'` → inline "Failed to load library", message + Retry button calling `refresh()`. WAS-OK.
- `status === 'ready'` and games empty → "No games yet" with copy pointing to scan / Settings. WAS-OK.
- `status === 'ready'` and search filter empty → previously just said "No matches" with no recovery. **FIXED** — added a Clear search button.
- Toast on first appearance of a load failure (deduped via `lastToastedError` ref) so users that navigate away still see the failure. WAS-OK.

What changed:
- src/pages/HomePage.tsx — empty state now offers "Clear search" when the user has typed a query that returns no results. Uses the existing `home__retry` token; no new CSS.

---

## src/pages/LibraryPage.tsx — FIXED (small)

State machine traced:
- `status === 'loading'` and no entries cached → editorial "One moment / LOADING LIBRARY". WAS-OK.
- `status === 'error'` → "Failed to load library" + Retry calling `refresh()`. WAS-OK.
- `filtered.length === 0` while `games.length > 0` → previously a single-copy message, no recovery. **FIXED** — now distinguishes "no entries on file" (library is empty) from "no games match the current filter" (filter wedge), and offers a Clear filters button that resets kind, source, and both search states.
- `filtered.length === 0` and the library is genuinely empty → updated copy points to Settings → Library / Files. **FIXED**.
- Source-chip auto-clear when a source vanishes from the library between scans. WAS-OK.

What changed:
- src/pages/LibraryPage.tsx — empty state branches by `games.length`, and the new Clear filters button only renders when at least one filter is non-default.

---

## src/pages/GameDetailPage.tsx — WAS-OK

State machine traced:
- `libraryStatus === 'error'` → renders dedicated "FAILED TO LOAD LIBRARY" panel with the error message and a Back button.
- `libraryStatus === 'loading' | 'idle'` and entry not yet found → "LOADING…" placeholder.
- `libraryStatus === 'ready'` and `byId(id) === undefined` → "NOT FOUND" with the offending id and a Back button.
- RAWG metadata fetch — `lookupRawg()` swallows network/IPC errors at the bridge layer and returns `null`, so the page always renders the local entry plus whatever metadata arrived. The cancellation `cancelled` flag prevents `setState` after unmount. WAS-OK.
- `onPlay` and `onToggleFavorite` both have try/catch with toast + inline error messages. WAS-OK.
- Lightbox traps focus, restores it, handles Escape/Tab. WAS-OK.

No changes were necessary.

---

## src/pages/SettingsPage.tsx — FIXED

State machine traced:
- Initial `config_get` failure previously left the user with DEFAULTS + a one-line warning notice; the Apply button stayed enabled, so they could overwrite their real config with defaults. **FIXED** — added a `reloadKey` and a Retry button in the warning notice that re-runs `config_get`. The form is still usable in the meantime, but the user has an obvious recovery path.
- Apply (`config_set`) failure → inline error + toast. WAS-OK.
- Autostart command failure during Apply is intentionally swallowed (per inline comment) so the rest of Apply still succeeds. WAS-OK.
- LibrarySection — scan failure shown inline; uses `useLibrary().refresh()` on success. WAS-OK.
- VoiceSection — `voice_get_devices` failure surfaces in the device hint; voice test errors shown inline; both promises wrap try/catch. WAS-OK.
- ControllerSection — polling rejection silently treated as "disconnected" (intended). WAS-OK.
- ServicesSection — Twitch OAuth start failure shown inline. WAS-OK.

What changed:
- src/pages/SettingsPage.tsx — initial-load error now offers a Retry button.
- src/pages/SettingsPage.css — added `.settings__notice-retry { margin-top: var(--s-sm); }` so the inline button doesn't crowd the message text.

---

## src/pages/OnboardingPage.tsx — WAS-OK

State machine traced:
- WelcomeStep — pure UI, no async. WAS-OK.
- LibraryScanStep — `listen('library:scan:progress')` is wrapped in try/catch with a fall-through to deriving per-provider state from the final `scanLibrary()` result list. `scanLibrary()` rejection sets `scanError` and unblocks Continue. The `cancelled` flag and `unlisten()` clean up if the user advances mid-scan. WAS-OK.
- VoiceMicStep — `getUserMedia` rejection sets `error` (denial / no device); the meter winds down via `stop()` and Continue unlocks via the `error !== null` clause. AudioContext is closed in `stop()`. WAS-OK.
- ControllerStep — listens for input via `useController`; no async, can't fail. WAS-OK.
- DoneStep / `finish()` — `setOnboarded(true)` failure is intentionally swallowed and navigation still happens, so the user is never trapped in onboarding. WAS-OK.

No changes were necessary.

---

## src/pages/FileManagerPage.tsx — FIXED

State machine traced:
- `getConfig` rejection → status='error', inline "Couldn't read the config" + Retry. WAS-OK.
- `entries.length === 0` and `status==='ready'` → "No manual entries yet…". WAS-OK.
- File / directory picker — Tauri's `openDialog` returns `null` on dismiss, which the `if (typeof result === 'string')` check naturally ignores. **HARDENED** — added an `isCancellation()` guard to the catch branch so any future plugin version that throws on cancel is still treated as a no-op rather than a hard error.
- Save (`saveConfig` + `scanLibrary`) — was already in try/catch with `formError`; the post-save `scanLibrary` call uses an inner try/catch since it's non-fatal. **FIXED** — now also fires a success toast ("Added X" / "Updated X") and an error toast on failure so the user gets confirmation regardless of where their attention is.
- Delete — same pattern; **FIXED** with a "Removed X" toast on success and error toast on write failure.
- Validation — `pathExists` returns null on permission errors (config-allowlisted path could refuse), so the validator only flags genuine missing files. WAS-OK.

What changed:
- src/pages/FileManagerPage.tsx — pulled in `useToast`, added success / error toasts on save & delete, hardened picker catch.

---

## src/api/LibraryContext.tsx — WAS-OK

State machine traced:
- `getLibrary()` failure → status='error', error string surfaced to consumers.
- Empty initial library → triggers a one-shot `scanLibrary()` (latched via `autoScanAttempted` ref so a later filter that produces zero rows doesn't restart it). Failure of the auto-scan also lands in status='error' with a useful message.
- `library:scan:done` event → bumps `reloadKey`, which re-runs `getLibrary()`.
- `cancelled` guard prevents `setState` after unmount.

Consumers (HomePage, LibraryPage, GameDetailPage, QuickResume) all read status/error
correctly and render accordingly. No changes.

---

## src/components/QuickResume.tsx — WAS-OK

State machine traced:
- `useLibrary().games` is always an array; while loading it's `[]`, while errored it's `[]`. The carousel gracefully degrades to "NOTHING YET" copy in both cases. WAS-OK.
- `launchGame()` failure → toast + clears the `launching` flag so the user can retry. WAS-OK.
- Selection clamps to `cards.length - 1` during render; the "remember position" cursor stays in `selected` so a transient list shrink doesn't reset the user's position. WAS-OK.
- Focus restore on dismiss — saved on mount, restored on cleanup. WAS-OK.

No changes were necessary.

---

## Other surfaces (not in scope, spot-checked)

- `src/api/ToastContext.tsx` — TTL-based dismiss, ID counter survives same-tick collisions, `setTimeout` not cleaned on unmount but the timer references the captured `dismiss` setter which is safe to call against a stale state. WAS-OK.
- `src/components/VoiceOverlay.tsx` and `VirtualKeyboard.tsx` — not in audit scope; not modified.
- `src/App.tsx` — `getOnboarded()` rejection caught with a comment-explained fallback ("assume onboarded"); `setCheckedOnboarded(true)` always fires via finally so we never wedge the routes. WAS-OK.

---

## Verification

- `npx tsc -b --noEmit` clean (run before and after the changes).
- Each page's loading → ready → error path hand-traced above.
- No new dependencies introduced.
- No styling tokens beyond the existing palette / spacing scale.
- No Rust changes.
- agents/STATUS.md and CONTEXT*.md untouched.

---

## Per-page summary

| Page                               | State    | Notes |
|------------------------------------|----------|-------|
| HomePage                           | FIXED    | Clear-search button on no-match |
| LibraryPage                        | FIXED    | Branched empty copy + Clear filters button |
| GameDetailPage                     | WAS-OK   | Loading / error / not-found all already covered |
| SettingsPage                       | FIXED    | Retry button on initial config_get failure |
| OnboardingPage                     | WAS-OK   | All async paths already guarded |
| FileManagerPage                    | FIXED    | Save / delete toasts + cancellation-tolerant picker |
| api/LibraryContext.tsx             | WAS-OK   | Provider already exposes status + error |
| components/QuickResume.tsx         | WAS-OK   | Empty + launch-error already handled |
