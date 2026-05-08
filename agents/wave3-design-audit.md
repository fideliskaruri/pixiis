# Wave 3 — Editorial Design Audit

Branch: `worktree-agent-a5cc82a59fb5dcf49` (off `wave1/integration` HEAD `c4a71bb`)
Source of truth: `src/styles/PALETTE.md` + `src/styles/tokens.css` + `src/styles/animations.css`
Files surveyed: all of `src/styles/*.css`, `src/components/*.css`, `src/pages/*.css`, `src/App.css`, `src/index.css`, plus inline `style=` props in `src/**/*.tsx`.

## Rule-by-rule audit

### 1 · Single-accent rule
`var(--accent)` / `#C5402F` may appear only on `▶ PLAY` buttons, `:focus-visible` outlines, and critical error states.

| | Count |
|---|---|
| Violations found | **1** |
| Violations fixed | 1 |
| Violations deferred | 2 (design call) |

Fixed:
- `src/components/VoiceOverlay.css` — `.voice-overlay__dot` background was `var(--accent)`. The dot is a "listening" state indicator, not error/play/focus. Replaced with `var(--text)`.

Allowed under the rule (no change required):
- `src/components/Toast.css` — `.toast--error` border and `.toast__mark` background. `.toast__mark` is only rendered when `kind === 'error'` (verified in `Toast.tsx:40`). Both qualify under the "critical error states" exemption.
- `src/pages/FileManagerPage.css` — `.files__field--error`, `.files__field-error`, `.files__form-error` all use `--accent` for form-field error states. Allowed.
- `src/pages/OnboardingPage.css` — `.onboarding__glyph--err` and `.onboarding__error` use `--accent` for error indicators. Allowed.
- All `outline: 2px solid var(--focus)` and `box-shadow: 0 0 0 2px var(--focus)` usages — focus rings, allowed.

Deferred to design call:
- `src/pages/OnboardingPage.css` `.onboarding__primary--accent` — the "Open Pixiis" CTA on Step 5 of onboarding (`OnboardingPage.tsx:553`) intentionally uses the accent. The task brief flagged this exact case as deferrable.
- `src/pages/SettingsPage.tsx:297` "Apply" button uses the shared `.accent-btn` primitive (token-defined). The page's own header comment reads: *"Single accent only on the Apply CTA and focus rings — same rule as the rest of the app."* Both onboarding and settings use the accent CTA as a "commit / proceed" affordance pattern. Per the task spec ("PLAY only"), these are violations; per the codebase's own established convention, they're sanctioned. Defer.

### 2 · Type system
Display = Fraunces, body/UI = Inter, mono = IBM Plex Mono.

| | Count |
|---|---|
| Violations found | **0** in active code |
| Violations fixed | 0 |
| Notes | 1 (legacy file) |

All `font-family` declarations across `src/components/*.css` and `src/pages/*.css` reference token variables (`--font-display` / `--font-body` / `--font-mono`). No `Outfit`, `Roboto`, or `Helvetica` outside of fallback chains in active code. Inline `style=` props in `.tsx` files set only layout (`height`, `display`, `flex`, `top`, `left`, `width`); none set fonts or colors.

Note: legacy `src/styles/theme.css` (intentionally unimported, see Final-state list) declares an `Outfit` web-font import and a `--font: 'Outfit'` token — flagged below.

### 3 · No glass-morphism
No `backdrop-filter`, `backdrop:blur`, `box-shadow` glow effects, or `.glass-*` class names in active code.

| | Count |
|---|---|
| Violations found | **0** in active code |
| Violations fixed | 0 |

`grep -rn "backdrop-filter\|glass\|\.glass-"` against active code returns only descriptive comments ("no glass…"), the SearchBar tooltip text "Magnifying glass", and the legacy `theme.css`. No `.glass-*` class names anywhere.

`box-shadow` audit (4 hits):
- `SettingsPage.css` lines 315, 319, 380 — all `0 0 0 2px var(--focus)` — focus rings, allowed.
- `VirtualKeyboard.css:18` — `0 12px 48px color-mix(in srgb, var(--bg) 80%, transparent)` — positional dark drop shadow on the floating keyboard panel (not a glow halo). Reads as paper-over-paper elevation, not a luminous halo. Kept.

### 4 · No springs
Forbidden: any `cubic-bezier` whose y-values overshoot 1.0; framer-motion `spring`; overshoot timing functions.

| | Count |
|---|---|
| Violations found | **0** in active code |
| Violations fixed | 0 |

`grep -rn "cubic-bezier" src/ | grep -v "0.4, 0, 0.2, 1"` returns only legacy `theme.css`. All active CSS uses `var(--easing)` (= `cubic-bezier(0.4, 0, 0.2, 1)`), `linear`, or omits the timing function (default `ease`).

framer-motion is in `package.json` but not imported anywhere under `src/`:
```
$ grep -rn "framer-motion\|spring" src/ | grep -v ".css\|^/" | grep -v "no spring\|no springs\|no overshoot"
(no hits)
```

### 5 · Hard-coded colors
Any hex or `rgb()` / `rgba()` literal that isn't a token = smell.

| | Count |
|---|---|
| Violations found | **2** |
| Violations fixed | 2 |
| Documented exceptions | 1 |

Fixed:
- `src/components/Toast.css:51` — `.toast--success { border-color: rgba(237, 233, 221, 0.16); }` → `color-mix(in srgb, var(--text) 16%, transparent)`.
- `src/components/QuickResume.css:11` — `background: rgba(15, 14, 12, 0.8)` → `color-mix(in srgb, var(--bg) 80%, transparent)`. Comment added explaining it intentionally sits one notch heavier than `--scrim-md` (0.7).

Documented exception:
- `src/pages/LibraryPage.css:84` — the `.library__sort-select` chevron is a CSS `background-image: url("data:image/svg+xml;...")` whose SVG `stroke` is hard-coded as `%238A8478` (URL-encoded `#8A8478`, exactly `--text-dim`). CSS custom properties cannot be evaluated inside `url()` data URIs, so this is a necessary literal. The token's hex is duplicated, not a new color. Acceptable.

### 6 · Hard-coded font names
Forbidden: `Outfit`, `Roboto`, `Helvetica` outside of fallback chains.

| | Count |
|---|---|
| Violations in active code | **0** |
| Legacy file | 1 (deferred — unused) |

Active code is clean. `theme.css` is flagged below.

## Deferred / out-of-scope

- **`src/styles/theme.css`** — the legacy "Obsidian Glass" PS5 theme. **Not imported anywhere** (verified: `grep -rn "theme.css\|/theme'" src/` returns only doc comments noting it's intentionally not imported). Contains every flavour of violation in the audit (`Outfit` import, `--surface-glass` token, `--ease-spring` overshoot bezier `cubic-bezier(0.34, 1.56, 0.64, 1)`, hex-literal palette). PALETTE.md documents the plan: *"theme.css (PS5 glass) is still on disk for now — the Home restyle agent will sweep it. New code should not import it."* Anti-scope said "fix only token-rule violations" — the file has zero runtime impact, so deletion / sweep is deferred to whoever owns the cleanup.

- **OnboardingPage Step 5 accent CTA** — see Rule 1, deferred.
- **SettingsPage Apply CTA** — see Rule 1, deferred.

## Final state per CSS file

| File | State |
|---|---|
| `src/index.css` | clean |
| `src/App.css` | clean |
| `src/styles/tokens.css` | clean (token canon — left untouched per anti-scope) |
| `src/styles/animations.css` | clean |
| `src/styles/PALETTE.md` | clean (reference doc) |
| `src/styles/theme.css` | **has-deferred-issues** (unused legacy file, sweep deferred) |
| `src/components/NavBar.css` | clean |
| `src/components/SearchBar.css` | clean |
| `src/components/GameTile.css` | clean |
| `src/components/Toast.css` | fixed (1 hex → token) |
| `src/components/QuickResume.css` | fixed (1 rgba → color-mix token) |
| `src/components/VoiceOverlay.css` | fixed (1 single-accent violation) |
| `src/components/VirtualKeyboard.css` | clean |
| `src/pages/HomePage.css` | clean |
| `src/pages/LibraryPage.css` | clean (1 documented SVG-URL exception) |
| `src/pages/GameDetailPage.css` | clean |
| `src/pages/SettingsPage.css` | **has-deferred-issues** (Apply CTA accent — design call) |
| `src/pages/OnboardingPage.css` | **has-deferred-issues** (Step 5 CTA accent — design call) |
| `src/pages/FileManagerPage.css` | clean |

## Verification

- `npx tsc -b --noEmit` → exit 0 (clean).
- Hunt re-runs after fixes:
  - `grep -rn "backdrop-filter\|glass\|Outfit\b\|spring\b\|overshoot" src/` — only descriptive comments + the deferred `theme.css`.
  - `grep -rn "#[0-9a-fA-F]{3,8}" src/styles src/components src/pages | grep -v "var(--"` — only token canon (PALETTE.md, tokens.css), the deferred `theme.css`, and one explanatory comment in `GameTile.tsx`.
  - `grep -rn "cubic-bezier" src/ | grep -v "0.4, 0, 0.2, 1"` — only the deferred `theme.css`.
  - `grep -rn "rgba\|rgb(" src/components src/pages` — zero hits.

## Totals

| Rule | Found | Fixed | Deferred |
|---|---:|---:|---:|
| 1 · Single-accent | 1 | 1 | 2 (Apply + Onboarding Step-5 CTAs) |
| 2 · Type system | 0 | 0 | 0 (theme.css is unused) |
| 3 · No glass-morphism | 0 | 0 | 0 |
| 4 · No springs | 0 | 0 | 0 (theme.css is unused) |
| 5 · Hard-coded colors | 2 | 2 | 0 (1 documented SVG-URL exception) |
| 6 · Hard-coded font names | 0 | 0 | 0 (theme.css is unused) |
| **Total drift fixes** | **3** | **3** | **2 design calls + 1 unused-file sweep** |
