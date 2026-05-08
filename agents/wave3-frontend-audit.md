# Wave 3 — Frontend Audit

Branch: `worktree-agent-adb1e477b875bc4c2` (off `wave1/integration` HEAD `c4a71bb`).

Audit pass on the React/Tauri frontend looking for "merged but actually
broken" cases. Triggered by the user reporting two bugs that turned out
to be a stale build, but the broader question stood: what other cases
look fine in source but fall over at runtime?

`npx tsc -b --noEmit` is clean before and after every fix.

Status legend: **OK** / **FIXED** / **BROKEN-NEEDS-USER**.

---

## `src/App.tsx` — **OK**

Provider tree order is sound: `BrowserRouter > ToastProvider >
LibraryProvider > VirtualKeyboardProvider > QuickResume > AppContent +
VoiceOverlay`. Every consumer sits below its provider.

F11 listener cleans up on unmount. Onboarding-redirect effect is
guarded with a `cancelled` latch and runs once on mount. No orphaned
`<Placeholder>` references; no dead imports.

The `useEffect` that consults `getOnboarded()` includes a
`react-hooks/exhaustive-deps` disable to keep it run-once — that's
intentional and called out in a comment.

---

## `src/api/LibraryContext.tsx` — **FIXED**

Two bugs:

1. **Auto-scan latch flipped before the scan resolved.** The known one.
   `autoScanAttempted.current = true` ran before the `scanLibrary()`
   promise settled. A transient first-launch error (cold storefront,
   network blip) permanently disabled the silent first-launch scan for
   the rest of the session — every subsequent reload would skip it.

   Replaced the boolean latch with a counted retry: up to
   `MAX_AUTO_SCAN = 3` attempts, only counted when a scan actually
   fired, and pinned to the cap on the first success so a later
   reload-on-empty-list (e.g. user uninstalled everything) doesn't
   re-trigger another scan.

2. **Provider double-fires the scan during onboarding.** `LibraryProvider`
   mounts at the app root and fires its own auto-scan on the empty
   library. But on first launch the user is also redirected to
   `/onboarding`, where `LibraryScanStep` runs its own `scanLibrary()`.
   Two parallel scans serialise on the backend, the second clobbers the
   first's report, and the onboarding step appears to "do nothing".

   Fixed by checking `window.location.pathname === '/onboarding'` and
   skipping the auto-scan in that case — onboarding owns the first-run
   flow; the provider just reads what's persisted.

The `library:scan:done` event listener cleanup is correct (awaited
unlisten, called in cleanup) — only one listener is mounted across the
provider's lifetime.

---

## `src/api/bridge.ts` — **FIXED**

Three issues:

1. **`voiceStop()` had the wrong return type.** Bridge typed it as
   `string`; Rust returns the full `TranscriptionEvent` struct
   (`{ text, is_final, timestamp }`). A frontend that called
   `voiceStop()` and used the unwrapped value would render
   `[object Object]` in a search bar. Today only `SettingsPage` calls
   `voice_stop` directly (with a defensive `TranscriptionEvent | string`
   cast), but the bridge export is still a public API.

   Updated to return `Promise<TranscriptionEvent>`, with a defensive
   string-fallback for stub builds that still return bare text.

2. **`console.log('[scan]', result.providers)`** debug cruft inside
   `scanLibrary()`. Removed; the same data is persisted to
   `%APPDATA%\pixiis\scan_debug.log` by the backend, and the
   `scanLibraryWithReport` variant exists for surfaces that want it.

3. **No `try/catch` audit findings beyond the above.** Every other
   `invoke()` either has a try/catch at the call site or surfaces the
   reject via React state (e.g. `LibraryProvider` sets
   `status: 'error'`). `lookupRawg` swallows rejection and returns
   `null` — by design.

---

## `src/api/ToastContext.tsx` + `src/components/Toast.tsx` — **OK**

Provider sits at the app root and never unmounts in the normal
lifecycle. Each toast has its own `setTimeout(dismiss, TTL)`; ids come
from a `useRef` counter so simultaneous fires can't collide. Functional
state updates inside `setEntries` make the "5 toasts in one tick" case
race-free.

The timer-on-unmount edge case (timer outlives provider) only matters
during hot-reload, and a stray `setEntries` after unmount is a benign
React warning rather than a real defect.

---

## `src/components/QuickResume.tsx` — **OK** (relies on the spatial-nav fix)

Listener mounts at provider scope so Start works as a global toggle.
Empty `games` list is handled (`cards.length === 0` → "Nothing yet"
empty state). Selection is clamped during render, not in an effect.
Restore-focus on close.

The B-button conflict with the global `useSpatialNav.history.back()`
is fixed in `useSpatialNav.ts` (see below) — when QuickResume is open
B closes the panel only, not also pop a route.

---

## `src/components/VirtualKeyboard.tsx` — **FIXED**

Activation policy reads `lastGamepadAt.current` against
`RECENT_GAMEPAD_MS = 1500`. Initial `0` makes pre-controller focuses
fail the check correctly; far-past activity also fails (monotonic
`performance.now()`).

**Bug:** the panel did not close when the input lost focus. If the user
clicked elsewhere or the input unmounted, the on-screen keyboard
remained pinned to a now-stale target.

Added a `blur` listener on the target that, after a one-tick delay
(to skip transient blurs caused by the keyboard's own click handlers),
checks whether focus moved off the input and outside the panel — if
so, calls `onClose()`.

---

## `src/components/VoiceOverlay.tsx` — **OK**

All three Tauri event listeners are awaited and unsubscribed in
cleanup. A `cancelled` flag covers the strict-mode double-mount case
(if the cleanup runs before the `Promise.all` resolves, the resolved
unlisten functions are immediately invoked).

Two-phase visibility (`mounted` + `visible`) lets the fade-out animation
play before unmount. Both timers (`autoHideTimer`, `unmountTimer`) are
torn down in a separate unmount-only effect.

---

## `src/components/NavBar.tsx` — **OK**

F11 lives at the App level (window-scoped). Double-click on the navbar
toggles fullscreen, with a `closest('button, a')` guard so clicks on
tabs and window controls don't trigger it. `data-tauri-drag-region` on
the nav element; every interactive child sits under
`data-tauri-drag-region="false"` (logo, tabs, controls), so buttons
take their click events as expected.

`onResized` listener is awaited and unsubscribed in the cleanup.

---

## `src/pages/HomePage.tsx` — **OK**

`is_game` filter is applied before sorting. Search is direct (filter on
every keystroke) — the Library page is the one that debounces. Sort
modes (`az` / `recent`) both float favorites to the top first.

Error toast is gated on `lastToastedError` so navigating between pages
doesn't re-fire it. `useEffect` deps are correct.

---

## `src/pages/LibraryPage.tsx` — **OK**

Filter chips render only for sources with ≥1 entry. If the active
chip's source falls out of the available set, an effect drops it back
to `null`. Sort dropdown handles all four modes; `addedAt` is a
best-effort lookup against several metadata keys.

Search is debounced 300 ms via a `setTimeout` cleared on the next
keystroke. Empty states cover all three branches (error / loading /
no matches).

---

## `src/pages/GameDetailPage.tsx` — **OK**

RAWG fetch is keyed on `(game.id, game.name)` to avoid redundant
network calls when the entry's array reference flips. Failure is
non-fatal (page renders without RAWG metadata; `lookupRawg` returns
`null` on error).

Hero mode (`banner` vs `poster`) handles missing background_image.
Image `<img>` tags pass through `imageUrl()` which only proxies file://
paths through `convertFileSrc`. Lightbox cleans up its keydown listener
and restores focus to the trigger.

The `launchedTimer` is torn down on unmount.

---

## `src/pages/SettingsPage.tsx` — **OK**

Apply persistence is real (uses `config_set` with the dotted-section
patch). Each section round-trips through `fromConfig` → state →
`toPatch`. Voice test panel handles missing devices (shows the pending
hint) and a missing model (the `voice_stop` rejection path sets
`voiceError`).

The voice-test sub-effect uses `eslint-disable-next-line` to avoid
re-firing on `state.voice_mic_id` changes — intentional and commented.

The controller-state polling effect cleans up its interval. The
`savedTimer` is torn down on unmount.

---

## `src/pages/OnboardingPage.tsx` — **FIXED**

Two issues:

1. **`finish()` had a redundant if/else.** Both branches called
   `setOnboarded(true)`. Collapsed to one call; Skip and Done now share
   the same path explicitly. The intent ("skip also marks the user as
   onboarded") is documented inline.

2. **`ControllerStep`'s 320 ms fade timers were never cleaned up.** If
   the user advanced (or skipped) with a button still being released,
   the queued `setTimeout` would `setPressed(...)` on an unmounted
   component → React warning. Now tracked in a `useRef<number[]>` and
   cleared on unmount.

The library-scan step's listener is awaited and unsubscribed; a
`cancelled` ref covers strict-mode double-mount.

---

## `src/pages/FileManagerPage.tsx` — **OK**

File picker (`@tauri-apps/plugin-dialog`) is awaited and errors land in
`formError`. Manual entries persist via `getConfig` → patch →
`saveConfig`, then `scanLibrary()` is called so the new row materialises
immediately (failure is non-fatal — entry is already saved).

Validation runs before save; collisions are detected; existence check
is best-effort (`null` from the fs plugin means "can't verify" rather
than "missing").

The auto-focus-on-form-open effect deps include `selectedIndex` so
re-selecting the same index re-focuses correctly.

---

## `src/hooks/useController.ts` — **FIXED** (small surgery)

Replaced `prevState.current = {} as any` with a properly typed
`Partial<Record<ControllerButton, boolean>>` — same runtime behavior,
no `any`.

The 60Hz `requestAnimationFrame` loop runs once per `useController()`
caller. Today that's QuickResume (×2 — outer + Panel),
VirtualKeyboardProvider, VirtualKeyboard panel (when open),
ControllerStep, and `useSpatialNav` — five-to-six concurrent rAF loops
all polling the same gamepad. Not a correctness bug, but it's wasted
work; consider centralising in a future pass. **Out of scope for this
audit.**

---

## `src/hooks/useSpatialNav.ts` — **FIXED**

**Bug:** The B-button handler called `window.history.back()` globally.
When QuickResume / VirtualKeyboard / Lightbox were open, their own
B-handlers closed the modal AND `useSpatialNav` simultaneously popped a
route — one button press, two surfaces deep.

Now skips `history.back()` when any element matching
`[role="dialog"][aria-modal="true"]` is in the DOM. QuickResume,
VirtualKeyboard panel, and Lightbox all set `aria-modal="true"`, so
their B-handlers run uncontested.

The spatial search itself (left/right/up/down candidate scoring) is
unchanged.

---

## Out-of-scope notes for the user

- `framer-motion` is in `package.json` but not imported anywhere. Safe
  to drop in a future cleanup.
- `useController` runs N concurrent rAF loops (one per consumer).
  Centralising into a shared store + observer pattern would be a
  separate pass.
- `scanLibraryWithReport` is exported but currently unused — kept as
  public API for surfaces that want the per-provider report.

---

## Bugs found / fixed this pass

1. `LibraryContext` auto-scan latch (transient errors locked it out) — **FIXED**
2. `LibraryContext` double-scan with onboarding — **FIXED**
3. `bridge.voiceStop()` wrong return type (string vs TranscriptionEvent) — **FIXED**
4. `bridge.scanLibrary` `console.log` debug cruft — **FIXED**
5. `useSpatialNav` B-button history.back fires alongside modal close — **FIXED**
6. `VirtualKeyboard` doesn't close on input blur — **FIXED**
7. `OnboardingPage` ControllerStep timers leak on unmount — **FIXED**
8. `OnboardingPage` finish() redundant branch — **FIXED**
9. `useController` `as any` typing — **FIXED**

Total: 9 fixes in one commit. No items in **BROKEN-NEEDS-USER**.
