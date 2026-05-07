# Wave 3 — Final Review Pass

Branch: `wave1/integration` · HEAD reviewed: `d085d95`

Two-track sweep: editorial design consistency (CSS + components) and
code quality (Rust + TypeScript). Inline fixes applied where the cost
was a one-liner; everything larger documented below with severity and a
suggested next step.

---

## Part 1 — Editorial design sweep

### Theme.css legacy file

`src/styles/theme.css` (147 lines, PS5 obsidian glass) is on disk but
**not imported anywhere** — `App.tsx` line 23 explicitly notes this and
`index.css` only pulls in `tokens.css` + `animations.css`. The Wave 1
brief left it in place. No leak.

The side effect is that the global reset (`*::before/::after`,
`html/body/#root` sizing, scrollbar, selection) lived only in
`theme.css` and was therefore **not running**. Fixed inline by moving an
editorial reset into `tokens.css`. Browsers were defaulting to user-agent
margins and box-sizing; this would have shown up as off-by-a-few-pixels
shifts in the next layout pass.

### Glass-morphism leaks scan

Searched every `*.css` and `*.tsx` for `backdrop-filter`, `.glass-`,
`coral`, `Outfit`, springy `cubic-bezier(*, 1.X, *)` curves, and
Framer Motion `spring` configs.

| Surface              | Result                                          |
|----------------------|-------------------------------------------------|
| `tokens.css`         | clean                                           |
| `animations.css`     | clean — no springs, no bouncy curves            |
| `theme.css` (legacy) | glass intact but unimported — leave             |
| `NavBar.css`         | clean                                           |
| `GameTile.css`       | clean                                           |
| `SearchBar.css`      | clean                                           |
| `HomePage.css`       | clean                                           |
| `GameDetailPage.css` | clean                                           |
| `SettingsPage.css`   | 2 accent leaks (fixed inline, see below)        |
| `OnboardingPage.css` | 3 accent leaks (documented, larger fix)         |
| `FileManagerPage.css`| 4 accent uses on form errors (deliberate)       |
| `App.tsx` / hooks    | no Framer Motion in the project at all          |
| `*.tsx`              | no `framer-motion`, no `spring/stiffness/damping` |

### Single-accent rule audit

Every `var(--accent)` / `#C5402F` / `coral` reference was inspected.

**Compliant uses (PLAY + focus only):**
- `tokens.css` — `.accent-btn` definition (the ▶ PLAY primitive).
- `tokens.css` — `--focus: #C5402F` and `--accent` token.
- Every `:focus-visible { outline: 2px solid var(--focus); … }` across
  components and pages — the focus ring contract.
- `GameDetailPage.tsx` — `.accent-btn detail__play` is the ▶ PLAY CTA.
- `SettingsPage.tsx` — `.accent-btn settings__apply` is the **Apply**
  CTA. Same pattern as PLAY (single primary commit on the page); reads
  as on-brief.

**Violations fixed inline:**
- `SettingsPage.css` `.settings__twitch-status--error` — was
  `color: var(--accent)` for the "Failed" badge. Now `var(--text)`; the
  word "Failed" carries enough on its own.
- `SettingsPage.css` `.settings__notice--warn` — was
  `border-left-color: var(--accent)`. Now `var(--text)`; warnings stay
  in the neutral palette.

**Violations documented (need design call, not silent edit):**
- `OnboardingPage.css` `.onboarding__primary--accent` (used on the final
  "Open Pixiis" button on the Done step) — a coral CTA. Either rebrand
  this as a true ▶ PLAY-tier action (and rename the class to
  `.accent-btn` for consistency) or strip the modifier and let it ride
  on the neutral `.onboarding__primary` like every other Continue
  button. **Suggested fix:** drop the `--accent` modifier; the bordered
  primary is enough — the page already crescendos with serif type.
- `OnboardingPage.css` `.onboarding__glyph--err` (✕ on a failed
  scanner) and `.onboarding__error` (mic permission error text) — coral
  for error state. Per strict brief, these should be `var(--text)` with
  the glyph itself doing the work (✕ vs · vs ✓). **Suggested fix:** swap
  both colours to `var(--text)`; the symbol carries the error meaning.
- `FileManagerPage.css` — four uses (`.files__field--error`,
  `.files__field-error`, `.files__form-error`, the file's header
  comment) intentionally use `--accent` for inline form validation. The
  file's header **explicitly** documents this exception ("Single-accent
  rule preserved — red is reserved for the inline form errors plus the
  focus ring."). This is a deliberate scope expansion, not a leak —
  flagging only because the strict reading of the brief is "PLAY +
  focus, nothing else." **Suggested call:** keep as is or escalate the
  exception into PALETTE.md so future agents know it's allowed.

### Motion audit

- No `framer-motion` import anywhere in the tree (`grep -r framer-motion
  src/` is empty). Tile focus is a CSS transition; page transitions are
  the `.fade-in` keyframe; nothing else moves.
- `cubic-bezier` use: `tokens.css` defines the editorial easing
  (`cubic-bezier(0.4, 0, 0.2, 1)` — a true ease-in-out, no overshoot).
  Every transition in components references `var(--easing)`, never an
  inline curve. `theme.css` still has the `--ease-spring`
  `cubic-bezier(0.34, 1.56, 0.64, 1)` overshoot — but it's unimported.
- `prefers-reduced-motion` is honoured in `animations.css` and
  `OnboardingPage.css`.

### Inline editorial fixes (this PR)

| File                       | Change                                       |
|----------------------------|----------------------------------------------|
| `src/styles/tokens.css`    | Added global reset + #root sizing + scrollbar + selection (had silently regressed when theme.css was orphaned). |
| `src/pages/SettingsPage.css` | `.settings__twitch-status--error` accent → text. |
| `src/pages/SettingsPage.css` | `.settings__notice--warn` accent border → text. |
| `src/index.css`            | Stale "Reset handled by theme.css" comment refreshed. |
| `src/App.css`              | Stale "All styles in theme.css" comment refreshed. |

---

## Part 2 — Code review

### High severity

None. The runtime path doesn't have any obvious crash bugs.

### Medium severity

**1. `bridge.ts saveConfig()` arg-name mismatch with the Rust command.**
The Rust `config_set(_patch: Map<...>)` exposes its parameter as `patch`
(Tauri strips the leading `_`). `SettingsPage.tsx` calls it correctly
(`{ patch: toPatch(state) }`), but `bridge.ts saveConfig` was sending
`{ values: config }`. Today the Rust impl is a stub that ignores the
arg (`Ok(())` regardless), so nothing visibly breaks — but
`FileManagerPage.tsx` writes its manual-apps list through `saveConfig`,
which means **the moment the config_set stub is filled in, manual game
entries will silently fail to persist**. Fixed inline.

**2. `library_scan` swallows worker-thread join errors.**
`commands/library.rs:21` — `tokio::task::spawn_blocking(move || svc.scan()).await.unwrap_or_default()`.
If the scan thread panics, the user sees an empty library with no
error. Suggested: keep the `spawn_blocking` for non-blocking IO but
surface the join error as `AppError::Other(...)` so the frontend
`status: 'error'` branch lights up.

**3. Provider trait can't report failure per provider.**
`library/mod.rs::Provider::scan(&self) -> Vec<AppEntry>` returns Vec,
not Result. The dispatch loop (`mod.rs:84-101`) iterates the providers
and merges their entries — already graceful in that one provider's
empty scan doesn't kill another, **but** an internal error inside one
provider has nowhere to go: it either silently returns an empty Vec or
panics the whole scan. The onboarding flow already speaks the language
of per-provider state (`done | error | unavailable`), and the
backend emits `library:scan:progress` events that include an `error`
field — but providers themselves can't fill it in. Suggested:
`fn scan(&self) -> Result<Vec<AppEntry>, ProviderError>` so the
registry can emit per-provider error events without losing the rest.

### Low severity / cleanup

**4. `SettingsPage.tsx::AboutSection` declares `update` it never calls.**
`AboutSection({ state, update })` — `update` is in the destructure but
only `update('autostart', ...)` is exercised through it. Not a bug;
just noting that the prop is partially used. (No fix; refactor would
churn.)

**5. `SearchBar.tsx` had a debounce timer firing into an empty
callback.** Removed inline. The mount paid for a `setTimeout` per
keystroke that did nothing. Net: simpler component, slightly less
allocation.

**6. Controller spawn loop has no shutdown signal.**
`controller/mod.rs::spawn` enters an unconditional `loop { ticker.tick().await; … }`.
That's fine because Tauri tears down the runtime on app exit, but if a
future test wants to construct a `ControllerService` and exercise it
without the full Tauri runtime, the loop will leak. Suggested:
`Notify`-based cancel token threaded through `spawn`; not blocking.

**7. `lib.rs::run` ends with `.expect("error while running tauri
application")`.** Standard Tauri boilerplate — keep. It only fires if
the entire Tauri runtime can't start, which is unrecoverable.

**8. `voice/pipeline.rs` worker spawn `expect`s.**
`spawn_rolling_worker` and `spawn_transcribe_worker` use
`.expect("spawn rolling worker")`. `thread::Builder::spawn` only fails
if the OS refuses to allocate a thread — at that point the app is
already in trouble. Acceptable.

**9. `voice/tts.rs` has 3 `unwrap()` calls.** Two are in
`#[cfg(test)]` blocks (`vocab::Vocab::embedded().unwrap()`); one is
`CString::new("en-us").unwrap()` for a static literal that cannot
contain interior NULs. All defensible.

**10. `lib.rs` — voice service init failure is handled gracefully.**
Whisper model missing → `VoiceServiceSlot { service: None, init_error:
Some(msg) }` is managed. Subsequent commands return
`AppError::Other("voice unavailable: ...")`. Clean degradation.

### Frontend error handling audit

Every `invoke()` call site I could find had its rejection handled:

- `bridge.ts` — `lookupRawg` wraps in try/catch, returns null;
  `getLibrary` / `scanLibrary` / `launchGame` / `toggleFavorite` /
  `searchLibrary` / `voiceStart` / `voiceStop` / `getConfig` /
  `saveConfig` / `getOnboarded` / `setOnboarded` are bare `invoke`
  calls — each caller wraps them.
- `LibraryContext.tsx` — `getLibrary().then(…).catch(…)`. Good.
- `HomePage.tsx` — reads from context; no direct invoke.
- `GameDetailPage.tsx` — `onPlay`, `onToggleFavorite` both `try/catch`
  and surface error state. RAWG lookup is wrapped in `bridge.ts`.
- `SettingsPage.tsx` — every section's `invoke` call has either a
  `Promise.then(_, errCb)` or a `try/catch` and writes the message into
  state.
- `OnboardingPage.tsx` — `setOnboarded` failure swallowed by design
  (comment: "still navigate so the user isn't stuck"). `scanLibrary`
  failure is captured into `scanError`. Mic `getUserMedia` failure is
  captured into `error`.
- `FileManagerPage.tsx` — `getConfig` / `saveConfig` / `scanLibrary`
  are wrapped in try/catch.

No bare `invoke` without a handler. No `console.log` debug cruft. No
HTTP `fetch()` calls outside `invoke` — `imageUrl()` correctly routes
local paths through `convertFileSrc`.

### Routing / app shell

- `App.tsx` covers `/`, `/library`, `/game/:id`, `/files`, `/settings`,
  `/onboarding`. All present. `/library` is still a placeholder.
- Onboarding-redirect logic uses a `checkedOnboarded` flag and only
  fires once on mount — no infinite loop. The marker check failure is
  handled (assume onboarded so the user isn't trapped).
- **Minor UX gap:** `NavBar.tsx::NAV_ITEMS` doesn't include `/files`,
  so the route is reachable only programmatically. Out of scope for
  this review (probably intentional for the editorial chrome) but worth
  flagging to design.

### Empty-state coverage

- `HomePage` — handles `error`, `loading`, no-results-from-search,
  no-games-yet.
- `GameDetailPage` — handles library-load-error, library-loading,
  not-found-by-id, plus per-action errors (launch, favorite).
- `SettingsPage` — `loaded === false` shows LOADING; `loadError` shows
  a notice over the form; per-section the soft-deps surface "Pending"
  hints when commands aren't wired.
- `OnboardingPage` — every step has its own loading/error/empty
  surface.
- `FileManagerPage` — `loadError` surface, empty list copy, per-field
  validation.

No `undefined.foo` crash potential I could find.

---

## Summary

- **Editorial leaks found:** 9 (theme.css orphaned reset; 2 settings
  accent leaks; 3 onboarding accent uses; 4 deliberate file-manager
  accent uses on errors; 2 stale code comments).
- **Inline fixes:** 5 (the orphaned reset, both settings leaks, and
  both stale comments + bridge.ts arg name).
- **Documented for follow-up:** OnboardingPage `--accent` modifier on
  the final CTA + error states; per-provider scan error reporting;
  `library_scan` join-error masking; FileManagerPage red-on-error
  exception (escalate or codify in PALETTE.md).
- **Bugs:** 1 medium (`bridge.ts` arg-name mismatch — fixed inline).

No `console.log`, no rogue `fetch`, no Framer Motion springs, no
`backdrop-filter`, no `Outfit` font references in any imported file.
The PS5 glass theme is fully quarantined to the orphan `theme.css`.
