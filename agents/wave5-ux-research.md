# Wave 5 — UX research & design recommendations
## Couch + controller + TV experience for Pixiis

**Owner:** UX research (this doc).
**Audience:** the implementation agents in the next wave.
**Mission as set by user:**
> "look for xbox mode and steam big screen ... imagine what the user wants when they have plugged in their pc to the tv ... probably don't want to fiddle. every single fucking area of the ui should be toggled and accessible using a controller."

This is a brief, not a code change. Read it linearly. The "Top 10" and "Contracts" sections are the bits the next wave will work against.

---

## 1. Personas

**Casual TV gamer (primary).** Plugged the PC into the living-room TV ten minutes ago. Sitting on the couch with an Xbox controller. Won't touch the keyboard. Doesn't want to read. Has 25–80 games across Steam + Xbox. Wants to see the cover art for *Hades*, press A, and play. If anything makes him stand up and walk to the keyboard, the launcher has failed.

**Power user (secondary).** Knows what RAWG is. Edited a config.toml once. Will use voice search if it's instant; will give up forever if "voice model not available" shows up twice. Cares about the Settings page being legible. Will rebind the global summon hotkey within 30 seconds of installing.

**First-time user (tertiary).** Brand new to Pixiis. Has plugged the controller in but doesn't know whether D-pad or stick navigates, doesn't know which button is "back," doesn't know there's a search shortcut. Will discover features only if the UI shows them. Onboarding gets 20 seconds of attention before he skips it.

---

## 2. Findings from research

Sources cited inline. Quoted claims point at a URL.

### 2.1. Xbox / 10-foot canon

- **32 epx minimum control height; default scale factor 200% on Xbox; 1080p target render.** Ship a UI that "looks great at 960×540 px at 100% scale" and the Xbox upscale will handle the rest. Source: [Designing for Xbox and TV — UWP](https://learn.microsoft.com/en-us/windows/apps/design/devices/designing-for-tv).
- **Body text floor is 15 epx. Captions / metadata floor 12 epx.** Same source.
- **TV-safe area: avoid placing essential UI within 27 epx top/bottom or 48 epx left/right.** "Draw only non-essential visuals within 5% of the screen edges." Same source.
- **No more than six clicks edge-to-edge.** Same source.
- **Search affordance convention: Y opens search.** "If your app provides a search experience, it is helpful for the user to have quick access to it by using the **Y** button on the gamepad as an accelerator." Same source. (Pixiis currently uses **X**. See diagnosis.)
- **When the search experience opens, the on-screen keyboard should appear already opened.** Same source.
- **Persistent "back" prompt at the bottom-left of every page.** "Players are always provided the ability (and the important visual interaction prompt on the bottom-left corner of the screen) to press 'B' to go back to the previous menu screen." Source: [Xbox Accessibility Guideline 112](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/112).
- **Components repeated across screens must appear in the same relative order.** "When dialog boxes appear, interaction prompts also appear on the bottom of the window." Same source. The button-hint footer is **the** consistent component on Xbox/Steam Deck.
- **Linear menus should loop on the last/first item; 2-D grids must NOT loop.** Same source. (Pixiis currently does neither.)

### 2.2. Steam Big Picture / Steam Deck

- **Big Picture displays a contextual button-prompt footer.** "The footer will swap to A/B/X/Y if an Xbox controller or Steam Controller is used." Source: [Steam Community thread on button glyphs](https://steamcommunity.com/groups/SteamClientBeta/discussions/0/3185738755276274147/).
- **Steam Deck UI is replacing Big Picture on desktop, and the desktop story is not actually solved yet.** "It's still not ideal for desktop use — especially on 4K monitors where scaling issues, oversized UI elements, and blurry text make the experience frustrating." Source: [Steam Deck UI replaces Steam Big Picture mode on Windows PCs (PCGamesN)](https://www.pcgamesn.com/steam-deck/ui-big-picture-mode-update). **Translation for us:** there's a clear opportunity to be better than Steam at the "PC plugged into TV" case specifically.
- **On Steam Deck, the on-screen keyboard does NOT auto-open on text-field focus reliably.** "When a user interacts with a typing field, you see the cursor but the keyboard does not open up automatically." User has to learn "Steam + X" to summon it. Source: [How to Open Keyboard on Steam Deck (Eneba)](https://www.eneba.com/hub/gaming-gear-guides/how-to-open-keyboard-on-steam-deck/). **Translation for us:** auto-open-on-focus is a feature Pixiis can ship that Valve hasn't shipped reliably. Worth doing well.
- **Big Picture is widely complained about — the bar is not high.** "Just so big and more difficult to navigate than the standard interface." "Store interface is broken: clicking on screenshots freezes the UI, navigation with up/down buttons highlights invisible parts of the UI." Source: [Big Picture Mode nobody uses or likes you (Steam discussions)](https://steamcommunity.com/discussions/forum/0/4030223299345810473/), [Store Navigation is broken with Controller](https://steamcommunity.com/groups/bigpicture/discussions/4/600766503721153543/).

### 2.3. Playnite

- **Playnite Fullscreen mode also runs into back-stack problems.** GitHub issue [Overlay to handle operations via controller](https://github.com/JosefNemec/Playnite/issues/3890): "Playnite's fullscreen mode is missing an important feature that all consoles have nowadays: the overlay menu."
- **Default controls in Fullscreen mode are documented:** A = open game detail, LB/RB = filter presets, F11 toggles fullscreen. Source: [Playnite Fullscreen Mode docs](https://api.playnite.link/docs/manual/gettingStarted/playniteFullscreenMode.html).
- **A/B "swap confirmation/cancellation" toggle exists for users coming from PlayStation.** Same source. Worth noting: Pixiis has *no* button-swap option today.

### 2.4. Plex / Apple TV / general TV-app patterns

- **Plex back-button complaints map directly to the Pixiis back-button complaints.** Users want a *single* level of back per press, never multi-level pop. Source: [Android TV back button should not skip multiple levels](https://forums.plex.tv/t/android-tv-back-button-should-not-skip-multiple-levels-back-to-the-library-collection/937257).
- **tvOS minimum focusable card: 250 × 150 pt.** Larger than typical desktop tiles. Source: [tvOS Layout HIG](https://developer.apple.com/design/human-interface-guidelines/tvos/visual-design/layout).
- **tvOS focus uses parallax + drop-shadow + scale, not just a border.** Source: [tvOS Focus Engine (Brightec)](https://www.brightec.co.uk/blog/tvos-focus-engine).

### 2.5. Tauri-specific gotchas

- **Frontend `keydown` listeners only fire when the webview has focus.** Source: [Global Keyboard Shortcuts in Tauri v2 — The Right Way and the Wrong Way (DEV Community)](https://dev.to/hiyoyok/global-keyboard-shortcuts-in-tauri-v2-the-right-way-and-the-wrong-way-2h6d). **Translation for us:** F11 in `App.tsx` and Ctrl+K in `QuickSearchProvider` will both silently fail when the user has clicked back into the desktop or another window, and on a TV setup that happens often.

---

## 3. Diagnosis of current Pixiis (page by page)

This section walks the user's specific complaints. Each item links the relevant file + line so the implementation agents can find the surface fast.

### 3.1. Settings page navigation is shit
> "no proper highlighting, can't navigate between controls cleanly"

Current state (`src/pages/SettingsPage.tsx`):
- 1,628 lines. Five sub-sections (LIBRARY / VOICE / CONTROLLER / SERVICES / ABOUT) loaded into one DOM at a time via `key={section}`.
- Layout is `aside.settings__nav` (left rail of section tabs) + `main.settings__panel` (form). The Apply button sits on the bottom of the *aside*, not the main panel. (See `SettingsPage.tsx:386-465`.)
- D-pad navigation: every section button is `data-focusable`. Each form field's control is `data-focusable`. There is no explicit focus order: `useSpatialNav` (`src/hooks/useSpatialNav.ts:43`) walks every focusable in the document and picks the geometric nearest. With ~25 form controls scattered across two columns, that gives the user an unpredictable "where's the focus going to land?" experience.
- `useAutoFocus('.settings__nav-item', [section, loaded])` (`SettingsPage.tsx:384`) re-focuses the LIBRARY tab every time the user changes section — including when they came from inside the panel. This *fights* the user.
- The visible focus indicator: `.tile-focus` styles only apply to game tiles. Form controls get the default browser `:focus-visible` outline (2px accent, offset 4px — `tokens.css:101`). The accent on a 12-px tracked label is weak from 10 feet away and is the *same* accent used for PLAY, breaking the design system's "single-accent rule."

Severity: **high.** The Settings page is the single most criticized surface in the user's message.

### 3.2. Window/keyboard shortcuts don't work
> "the rt shortcut and overlay don't even show up"

Current state:
- F11: `App.tsx:55-64` registers a `window.addEventListener('keydown', ...)` listener. Will not fire when the webview lacks focus. Tauri global-shortcut plugin is wired only for the summon hotkey (`SettingsPage.tsx:1006-1185`), not F11.
- Double-click NavBar to toggle fullscreen: `NavBar.tsx:60-64`. Only fires on mouse double-click. On a controller it is unreachable.
- Win+Up: this is the OS-level maximize, not Pixiis. The user reports it works — that's because Tauri's window has `core:window:allow-toggle-maximize` capability. Confirmed in wave4 final report.
- Ctrl+K Quick Search: `QuickSearch.tsx:94-104`. Same `window.addEventListener('keydown', ...)` pattern — same focus-loss vulnerability.
- F1 Shortcuts cheat sheet: `ShortcutsCheatSheet.tsx:181-190`. Same pattern.
- **RT-to-record voice:** I cannot find anywhere in the codebase that wires the right trigger to the voice flow. The user-reported feature "RT shortcut" is not implemented. `useController.ts:107-111` exposes `getRightTrigger()` but no consumer calls it, and no `voice_start` hold-to-talk handler exists. The Settings page exposes `ctrl_voice_trigger: 'rt' | 'lt' | 'hold_y' | 'hold_x'` (`SettingsPage.tsx:69`) — config is plumbed but the runtime never reads it.

Severity: **high.** The user's "RT shortcut and overlay don't even show up" is literally accurate: the trigger is not wired.

### 3.3. On-screen keyboard activation is broken
> "user expects: focus the search bar with D-pad → press A → keyboard pops up. Does that flow work?"

Current state (`src/components/VirtualKeyboard.tsx`):
- Activation policy: `onInputFocus` is called from `SearchBar.tsx:36-39`. The provider auto-opens iff `performance.now() - lastGamepadAt < 1500ms`.
- Trace the controller flow: D-pad to a `SearchBar` → `useSpatialNav` calls `next.focus()` on the input. That fires `onFocus` → `vkbd.onInputFocus()`. **The condition is `lastGamepadAt < 1500ms`.** That works iff the user moved the D-pad in the last 1.5 s. Mostly fine.
- **But:** the user says "press A → keyboard pops up." Today, A on a focused input *clicks* it (via `useSpatialNav.onButtonPress` → `active.click()`), which is a no-op for `<input>`. The keyboard already opened on focus. So the user's mental model is mismatched with the current behavior.
- **Bigger problem:** the user is not consistently making it to the search input. Spatial nav from a tile to the search bar across the page header is unreliable. `useSpatialNav` weights perpendicular distance 3× and "right of current" simply requires `tx > cx + 5`. The search bar is in the *header*, above the grid. From a tile in the second row of the grid, the "up" direction will land on the closest tile above, not the search bar (geometrically correct but UX-wrong).
- VirtualKeyboard's hint reads `A SELECT · B CLOSE · X BKSP · Y SPACE` (`VirtualKeyboard.tsx:380`). Good. But that hint only shows up *after* the keyboard appears. Before that, nothing tells the user the keyboard exists.

Severity: **high.** Specific fixes are obvious (see contracts § 5.3).

### 3.4. Voice search broken
> "voice model not available — persists. Even if we bundle the model, users hit it."

Current state:
- Wave 4 bundled `ggml-base.en-q5_1.bin` per the final report. The user's claim that it still surfaces means either (a) the bundled model isn't being found at runtime, or (b) some code path checks for a *larger* model name. Settings defaults `voice_model: 'large-v3'` (`SettingsPage.tsx:104`) — if the runtime tries to load `large-v3` and it isn't present, it errors out as "model not available." **This is the most likely culprit.**
- `VoiceOverlay.tsx` is purely declarative — it listens for `voice:state` events. If no event fires, no overlay shows. Combined with the missing RT wiring (§ 3.2), the voice feature is effectively dead.
- Discoverability is zero. There is no on-screen "hold RT to speak" hint, no microphone glyph in the navbar, no audible chime, no first-launch demo. The Onboarding `VoiceMicStep` (`OnboardingPage.tsx:226-348`) tests the *mic* with a level meter, but never demonstrates the actual hold-to-talk flow.

Severity: **high.** Multiple compounding bugs. Treat this as a stack: model default, RT wiring, discoverability, error message wording.

### 3.5. Couch-distance readability
> implicit: "imagine what the user wants when they have plugged in their pc to the tv"

Current state (`src/styles/tokens.css:32-39`):
- `--t-body: 16px` — Xbox docs floor is 15 epx, but only after 200% scale. At 100% scale on a 1080p TV, **16px is ~6.4mm tall on a 55" set, viewed from 10 feet**. Calculator: that's roughly 2.2 arcminutes — readable, but tight.
- `--t-label: 12px` — at 10 feet on the same 55", that's **just below the typical comfortable-reading floor (3 arcminutes)**. The label primitive is used everywhere (CONTINUE PLAYING, source badges, recencies). Users will squint.
- `body.is-fullscreen` rules in `animations.css:108-115` scale tile widths by `--ui-scale` (default 1.25 in fullscreen). **They do not scale font sizes.** The user can crank UI scale to 200% and the label is still 12 px.
- Tile focus: `.tile-focus:focus-visible` thickens border 1→2 px and scales 1.0→1.04 (`animations.css:33-38`). 4% scale at 200 px = 8 px movement, **too subtle** at 10 feet. tvOS uses parallax + drop-shadow + larger scale (~1.1).
- Game tile minimum size: 200 px width (normal) × 1.25 in fullscreen = 250 px. tvOS HIG floor is 250 × 150 pt (≈ 333 × 200 px on a 1080p TV). **We're underspeccing.**
- Default focus outline: 2 px accent, 4 px offset (`tokens.css:101`). At 10 feet on the SettingsPage form, a 2-px outline is **barely visible**.

Severity: **medium-high.** Easy wins available — see contract § 5.5.

### 3.6. Universal controller accessibility
> "every component must be reachable + activatable via gamepad alone"

Audit (every component, every focusable):

| Component | Reachable via D-pad? | Activatable via A? | Gaps |
|---|---|---|---|
| `NavBar` minimize/maximize/close | **No** — `[data-no-spatial]` excludes navbar from spatial nav | Yes via mouse only | Win+Up works for maximize; minimize and close are unreachable from controller. |
| NavBar tabs (Home/Library/Settings) | **No** — also excluded; LB/RB cycles instead | LB/RB triggers navigate | Fine — by design. But there's no visual hint that LB/RB does this. |
| Home greeting | n/a | n/a | Decorative. |
| Continue Playing rail / Recently Added rail | Yes | Yes (opens detail) | Y to favorite is *only* on tile; Y on rail tiles is unbound. |
| Surprise Me pill | Yes | Yes | Reachable via D-pad-up from grid, but ordering is geometric so users may not find it. |
| A-Z / Recent sort pills on Home | Yes | Yes | Same nav-discovery issue. |
| Library kind chips (All/Games/Apps) | Yes | Yes | Same. |
| Library source chips | Yes | Yes | Same. |
| GameTile | Yes | Yes (opens detail) | Y key handler is `e.key === 'y'` (`GameTile.tsx:66`) — only fires on physical keyboard 'y', not the **gamepad** Y button. **Bug.** |
| GameDetail PLAY / Favorite | Yes | Yes | OK. |
| GameDetail Back | Yes | Yes | B button also works (route-aware). OK. |
| GameDetail screenshot tiles | Yes | Yes | OK. |
| GameDetail trailer iframe | Yes (focusable) | Yes | YouTube iframe takes over its own focus once activated; B-back to leave is fine. |
| Settings section tabs | Yes | Yes | Auto-focus fights user (§ 3.1). |
| Settings form controls (sliders, selects, checkboxes) | Yes (after navigating into section panel from tabs — but the spatial walk is messy) | Yes | Sliders need left/right arrow once focused — D-pad left/right fires the spatial nav, **not** the slider value change. **Bug.** |
| Settings Apply button | Yes (it's `data-focusable` on the aside) | Yes | OK. |
| Settings → Controller → "Global summon hotkey" capture | Yes | Yes (button starts capture) | Capture itself listens for keyboard keydown. **No way to set the hotkey from a controller** — chord is keyboard-only. Acceptable, but there's no "use a default" affordance for the controller user. |
| Settings → Voice → "Hold to test" | Yes | **No** — handler is `onPointerDown` / `onPointerUp` only (`SettingsPage.tsx:782-787`). Press-and-hold on a button via gamepad activates the click, but does not generate pointerdown/up. **Bug.** |
| QuickResume modal | Yes | Yes | OK. |
| QuickSearch modal | Yes | Yes | OK. Y opens detail, A launches, B/X closes. |
| ShortcutsCheatSheet | Yes (close button only) | Yes | OK. |
| OnboardingPage Skip | Yes | Yes | OK. |
| OnboardingPage VoiceMicStep "Hold to speak" | Yes | **No** — same `onMouseDown`/`onTouchStart` pattern as Settings (`OnboardingPage.tsx:326-331`). **Bug.** |
| OnboardingPage ControllerStep | Implicitly working | Implicitly | Listens for raw button presses. No dual UI for keyboard testers. |
| FileManagerPage list | Yes | Yes | Long form; not in spec for this wave. |
| VirtualKeyboard panel | Yes | Yes | OK. |

**Summary of controller gaps:** GameTile Y-button is broken. Sliders + selects on Settings can't be adjusted by D-pad. "Hold to test/speak" buttons need a hold-A handler. NavBar window controls are unreachable. Onboarding ControllerStep doesn't help non-controller users.

Severity: **high** (multiple bugs).

### 3.7. Discoverability
> "how does a brand-new user know what buttons do what?"

Current state:
- **F1 cheat sheet exists** (`ShortcutsCheatSheet.tsx`). It is keyboard-only to open. There is no on-screen path. A new user cannot find it.
- **Per-modal hints exist** (e.g. QuickSearch footer reads `↑ ↓ MOVE · ENTER LAUNCH · Y DETAIL · ESC CLOSE`). Good, but only inside the modal.
- **No persistent button-hint footer.** The single biggest gap from the Steam Big Picture / Xbox playbook. Every page needs one.
- **No first-launch "hold A on a tile to play" prompt.** Onboarding has a "press any button" demo but that's it.

Severity: **high.**

### 3.8. Information architecture
> "Home / Library / Settings / Game Detail. Is this the right structure?"

Current top-level surfaces: `/`, `/library`, `/settings`, `/game/:id`, `/files`, `/onboarding`.

Comparing:
- **Steam Big Picture:** Home, Library, Friends, Players, Web Browser, Music, Settings.
- **Xbox dashboard:** Home, My Games & Apps, Microsoft Store, What's New, Achievements, Community.
- **Playnite Fullscreen:** Home (recently played + featured), All Games, Filter Presets, Settings.

Pixiis's three-tab top-level (Home/Library/Settings) is **lean and probably correct** for the launcher's scope. Two issues, though:
1. **Home and Library overlap heavily.** Both render the same grid of games. Home adds Continue Playing + Recently Added rails + greeting. Library adds source chips + sort options. From a couch user's perspective, "why are there two of these?" — there's no clear answer. Consider collapsing Library *into* Home, with the chips/sort moved to a single header.
2. **Files is hidden.** It's accessible from inside Settings but is rendered as a top-level route at `/files`. A controller user can't reach it without typing a URL. **It should be promoted to a Settings → Library sub-action, not a hidden route.** (Implementation may already do this; route exists for direct deep-link access.)

Severity: **medium.** The IA isn't *broken*, it's *redundant*.

---

## 4. Top 10 improvements ranked by impact

Each item has the same shape: **problem → recommended fix → files → rationale → must-do vs nice-to-have**.

### #1 — Universal controller-action footer (Steam-style "A: Select / B: Back / Y: Search / Menu: …")
**Problem.** Discoverability is the single highest-leverage fix. The user has no on-screen hint of what any button does until they bumble into a modal that has its own footer.
**Fix.** Persistent fixed-position footer at the bottom of every page, 48 px tall (TV-safe), reads from a per-page prop or context, displays glyph + verb pairs with a dot separator. Gets pre-baked verbs from a global default but each page can override.
**Files.** New `src/components/ActionFooter.tsx`, mounted in `App.tsx` next to `NavBar`. New `src/api/ActionFooterContext.tsx` so pages register their actions. Update every page to call `useActionFooter([...])`. Remove the in-modal footers (cheat-sheet, quick-search, virtual-keyboard) and let them register their own actions instead so the visual language is identical everywhere.
**Rationale.** Cited by Xbox docs, Xbox Accessibility Guideline 112, Steam Big Picture, Playnite. **The single most-cited TV-app affordance in any Microsoft / Valve doc.**
**Priority.** Must do.

### #2 — Wire RT (and the configured `ctrl_voice_trigger`) to voice search
**Problem.** The user reports "RT shortcut and overlay don't even show up." Confirmed: the configured trigger is never read at runtime; voice flow is unreachable from the controller.
**Fix.** New hook `useVoiceTrigger()` mounted in `App.tsx`. Reads `controller.voice_trigger` from config. On rising edge of the configured trigger, fires `voiceStart()` via the bridge; on falling edge, fires `voiceStop()`. The existing `VoiceOverlay` already handles `voice:state` / `voice:partial` / `voice:final`, so the panel will appear automatically once events flow.
**Files.** New `src/hooks/useVoiceTrigger.ts`. Wire into `App.tsx` next to `useSpatialNav` / `useBumperNav`. Use `getRightTrigger()` from `useController.ts:107-111` polled at 60 Hz. Surface "Hold RT to speak" in the action footer (#1).
**Rationale.** Today's behavior matches the user's complaint exactly. This unlocks the entire voice surface.
**Priority.** Must do.

### #3 — Fix the default voice model to the bundled one
**Problem.** Default `voice_model: 'large-v3'` in `SettingsPage.tsx:104`. Wave 4 bundled `ggml-base.en-q5_1.bin`. Result: first-launch users hit "model not available" until they hand-edit Settings.
**Fix.** Change default to `'base-en-q5_1'` (or whatever id matches the bundled file in the Rust voice loader). Show a "model bundled" badge next to the field so users know which one ships. Validate the field on Apply: if the user picked a model that isn't available locally, surface a download CTA or a clear "this model isn't installed" message rather than failing at first invocation.
**Files.** `src/pages/SettingsPage.tsx:104` (DEFAULTS.voice_model), and possibly the Rust-side loader to be permissive about quantization variants.
**Rationale.** Single-line config fix that erases the most-cited bug.
**Priority.** Must do.

### #4 — Settings page redesign for controller-first navigation
**Problem.** Detailed in § 3.1. Auto-focus fights users; D-pad nav lands unpredictably; visual focus indicator is too thin for 10-foot viewing.
**Fix.** See contract § 5.1 below for the full spec.
**Files.** `src/pages/SettingsPage.tsx`, `src/pages/SettingsPage.css`, `src/styles/tokens.css` (new `--focus-ring-width-tv` token), `src/hooks/useSpatialNav.ts` (sectioned-grid mode).
**Rationale.** User explicitly called this out. Highest user-perceived friction surface.
**Priority.** Must do.

### #5 — On-screen-keyboard discoverability + activation flow
**Problem.** § 3.3. The flow works *technically* but users don't know it exists, and "press A on a focused input" doesn't open it (it doesn't need to — focus does — but the user's mental model is wrong, so we should serve that model anyway).
**Fix.** See contract § 5.3. Two changes: (a) make pressing A on a focused, empty `<input>` re-trigger the keyboard if it was dismissed; (b) show a "press A to type" affordance in the action footer (#1) when an input is focused.
**Files.** `src/components/VirtualKeyboard.tsx`, `src/components/SearchBar.tsx`, action-footer wiring.
**Rationale.** Addresses the exact mental-model mismatch the user articulated.
**Priority.** Must do.

### #6 — TV-readable type scale + focus indicator
**Problem.** § 3.5. Body 16 px, label 12 px, focus outline 2 px — all too small at 10 feet.
**Fix.** New `body.is-fullscreen` overrides for `--t-body`, `--t-label`, `--t-caption`, plus a thicker `--focus-ring-width: 4px` and `--focus-ring-offset: 6px` in TV mode. Tile focus animation should scale 1.0 → 1.08 (not 1.04) and add a drop-shadow. Tile minimum size in TV mode bumps to 280 px wide (close to tvOS 250 pt).
**Files.** `src/styles/tokens.css`, `src/styles/animations.css`, `src/components/GameTile.css`. **No JS changes.**
**Rationale.** Pure CSS fix; biggest perceived improvement per LOC.
**Priority.** Must do.

### #7 — Slider / select / hold-to-talk controller bindings
**Problem.** § 3.6. Sliders ignore D-pad left/right; selects can't be opened with A in a useful way; "Hold to talk" buttons require pointerdown.
**Fix.** Augment `useSpatialNav.ts`:
- When `document.activeElement` is a range input, intercept D-pad left/right to fire `e.target.value -= step` / `+= step` instead of moving focus.
- When `document.activeElement` is a `<select>`, A press should programmatically open the dropdown via `.showPicker?.()` (Chromium 102+). Fall back to D-pad up/down on the option list.
- Hold-to-talk buttons: change the contract to *also* respond to a `data-hold-to-activate` attribute. The spatial-nav hook checks for this when A is pressed/released and dispatches synthetic pointerdown/up. Existing buttons (`SettingsPage.tsx`, `OnboardingPage.tsx`) get the attribute.
- Fix `GameTile.tsx:66`: the keyboard 'y' fallback works, but the *gamepad* Y is never wired. Add a `useController` listener inside the tile that calls `onFavorite` when `document.activeElement === this.tileRef`.
**Files.** `src/hooks/useSpatialNav.ts`, `src/components/GameTile.tsx`, `src/pages/SettingsPage.tsx`, `src/pages/OnboardingPage.tsx`.
**Rationale.** Removes per-component papercuts that compound on a controller.
**Priority.** Must do.

### #8 — Promote F11 + Quick Search hotkeys to Tauri global shortcuts
**Problem.** § 3.2. Frontend `keydown` listeners drop when the webview loses focus.
**Fix.** Register F11, Ctrl+K, F1 via `@tauri-apps/plugin-global-shortcut` (already used for the summon shortcut). The frontend listener can stay as a fallback. Use the global registration *only* when the window is the front-most. Be careful: if F11 toggles fullscreen *while another app is in front*, that's a misfire — gate on `getCurrentWindow().isFocused()`.
**Files.** `src/App.tsx`, `src-tauri` shortcut registration alongside the summon hotkey.
**Rationale.** Behaviour matches user expectation.
**Priority.** Nice to have. The frontend listener is enough for the couch case as long as the user keeps the app focused. Promote *only* if the user tells us they're losing focus.

### #9 — First-launch button-tour overlay
**Problem.** § 3.7. Users don't know features exist.
**Fix.** After Onboarding's existing controller-test step (`OnboardingPage.tsx:359-447`), add a 6th step: a tour of A/B/X/Y/Start/RT with one sentence each. Save a marker (`%APPDATA%/pixiis/.tour-done`) so it never re-runs. Offer "Show shortcuts" link from Settings → About that re-opens it.
**Files.** `src/pages/OnboardingPage.tsx`, `src/api/bridge.ts` (new `getTourDone`/`setTourDone`), `src/pages/SettingsPage.tsx` About section.
**Rationale.** First-time users are persona #3. This is the surface they see.
**Priority.** Nice to have. The action footer (#1) covers most of the same ground passively.

### #10 — Collapse Home/Library or differentiate them sharply
**Problem.** § 3.8. Two surfaces show the same grid with overlapping chrome.
**Fix.** Pick one:
- **Option A (recommended):** Make Home the editorial "what to play tonight" surface (greeting, Continue Playing, Recently Added, Surprise Me, Featured) with **no** raw grid. Library is the only place the full grid lives.
- **Option B:** Keep both surfaces, but make Home grid show *only* favorites + recents (curated subset), Library the full set with chips and sort. Today's Home shows the full grid AND the carousels — so the "Library" tab is duplicating Home's bottom half.
**Files.** `src/pages/HomePage.tsx`, `src/pages/LibraryPage.tsx`.
**Rationale.** Reduces couch-user cognitive load. "Where do I go to find X?" should have one answer.
**Priority.** Nice to have. Defensible to leave both as-is.

---

## 5. Specific contracts for the next wave

These are the implementation specs. The next wave reads § 5 and ships.

### 5.1. Settings page redesign

**Layout (TV-mode, fullscreen):**
```
┌────────────────────────────────────────────────────────────────────┐
│  [back]                                              [search disp] │
│                                                                     │
│  SECTION                                                            │
│  Library                          ┌──────────────────────────────┐ │
│                                   │  Providers                   │ │
│  ▌ LIBRARY                        │  ☑ Steam  ☑ Xbox  ☑ Epic …   │ │
│    VOICE                          │                              │ │
│    CONTROLLER                     │  Scan interval               │ │
│    SERVICES                       │  ◀━━━━━●━━━━━▶  60 min       │ │
│    ABOUT                          │                              │ │
│                                   │  Show all Xbox apps as games │ │
│                                   │  ☐ Disabled                  │ │
│  [APPLY]                          │                              │ │
│                                   │  Scan now                    │ │
│                                   │  [Scan Now]                  │ │
│                                   └──────────────────────────────┘ │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  A SELECT  ·  B BACK  ·  LB/RB SECTION  ·  Y APPLY                  │
└─────────────────────────────────────────────────────────────────────┘
```

**Focus rules:**
- On entry: focus lands on the active section's first form control, **not** the section tab. (Today: lands on the LIBRARY tab.) The user is here to *change something*, not to confirm what section they're on.
- LB/RB cycles sections. Today's `useBumperNav` cycles top-level pages (`/`, `/library`, `/settings`). Inside Settings, the bumpers should cycle the section instead. (Override on this route.)
- D-pad up/down inside the panel walks form controls *vertically only*. Never crosses into the section nav. Wraps at the ends (linear menu rule from XAG 112).
- D-pad left from the leftmost control jumps to the section nav. D-pad right does nothing past the rightmost control.
- Y button presses Apply from anywhere in the section. Add this to the action footer.
- B button on the section tab: returns to previous page (already implemented). B on a form control: returns focus to the section tab (give the user a way back to the macro nav).

**Visual:**
- Section nav: 240 px wide. Each tab: 60 px tall, vertical 12-px padding, full-width focus ring (4 px accent border, 6 px offset).
- Form panel: max-width 720 px. Each `Field` row: 96 px tall (was unspecified; today varies). Label on left in `.label`; control on right.
- Sliders: minimum 320 px wide track, 24 px tall thumb. Today's sliders use the browser default (~16 px).
- Selects: replace native `<select>` with a custom dropdown that opens centered, list of options as full-width rows, A to confirm. (Native `<select>.showPicker()` works on a controller via the Chromium fallback, but the popup is OS-styled and ugly. Custom is worth the LOC.)
- Apply button: 64 px tall, full section-nav width, accent background. Live always visible at the bottom of the section nav (today: already does this).
- Save state pill: appears next to Apply for 2 seconds after success. Today: already does this.

**Sections (unchanged content; just verify):**
- Library: providers, scan interval, "show all Xbox apps", scan-now.
- Voice: model, device, mic, energy threshold, test-button.
- Controller: deadzone, hold ms, vibration, voice trigger, summon hotkey.
- Services: RAWG key, YouTube key, Twitch OAuth.
- About: version, autostart, fullscreen, UI scale, display name, greeting toggles, weather, library export, system power.

### 5.2. Universal action footer

**Component contract.**
```ts
// src/components/ActionFooter.tsx
type FooterAction = {
  glyph: 'A' | 'B' | 'X' | 'Y' | 'LB' | 'RB' | 'LT' | 'RT' | 'START' | 'SELECT';
  verb: string;             // "Select", "Back", "Search", "Favorite"
  context?: string;         // optional secondary line; rendered dimmer
  onActivate?: () => void;  // optional — hover/preview hint, not the actual handler
};
```

**Layout:**
- Fixed-position bottom of viewport, `position: fixed; bottom: 0; left: 0; right: 0;`. Height 56 px in TV mode, 40 px in windowed.
- Background: `color-mix(in srgb, var(--bg) 92%, transparent)` with a 1 px top hairline (`var(--rule)`).
- Hidden when a modal is open with its own footer (cheat-sheet, quick-search) — those modals re-register their actions and the footer renders the new set.
- Hidden when no actions are registered. (Empty footer = empty bar = noise.)

**Glyph rendering:**
- Use a small SVG sprite or a font with the four face buttons. Simplest: render a 24 px round chip with the letter inside, color-coded (A green, B red, X blue, Y yellow — the universally-known Xbox palette). For LB/RB/LT/RT/Start/Select, render as 1.4× wide rounded rects with the abbreviation inside.
- Each action is a `<span>` with the glyph + " " + verb. Separator between actions: a centered dot (`·`) at 50% opacity.

**Default actions (when nothing is registered):**
- `A Select · B Back · LB/RB Switch tab · Y Search`

**Per-page registration:**
- HomePage: `A Open · Y Favorite · X Search · LB/RB Switch tab · Start Quick Resume · RT Voice`.
- LibraryPage: same as Home plus `LT/RT Filter` if filter chips are focused.
- GameDetailPage: `A Play · Y Favorite · B Back · RT Voice`.
- SettingsPage: `A Select · B Back · LB/RB Section · Y Apply · RT Voice`.
- QuickResume modal: `A Launch · B Close`.
- QuickSearch modal: `A Launch · Y Detail · B Close`.
- VirtualKeyboard panel: `A Type · B Close · X Backspace · Y Space`.
- Lightbox: `B Close`.
- ShortcutsCheatSheet: `B Close`.

**Implementation note:** the footer reads `useActionFooter()` from a context provider. Pages call `useEffect(() => setActions([...]), [])` on mount. When unmounting, clear actions to fall back to the default set.

### 5.3. On-screen keyboard activation flow

**Goal:** match the user's stated mental model: "focus the search bar with D-pad → press A → keyboard pops up."

**Today's behavior:** focusing the input *already* opens the keyboard (if gamepad activity was recent). Pressing A on the focused input is a no-op.

**Desired behavior:**
1. **D-pad to a search input** → focus event fires → `VirtualKeyboardProvider.onInputFocus` checks recency → opens keyboard. (Today: works.)
2. **A on a focused input** → if keyboard is *already* open, pressing A on the input dispatches a focus to the *first key of the keyboard* so the user can start typing with one more A press. If keyboard is *closed* (e.g. user previously dismissed it with B), reopen it.
3. **Action footer when input is focused:** "A Open keyboard · Y Voice · B Back".
4. **Inside the keyboard:** "A Type · B Close · X Backspace · Y Space" (today's `vkbd__hint` content), promoted to the action footer.
5. **Auto-close on input blur** is already implemented (`VirtualKeyboard.tsx:181-196`). Keep.
6. **Voice button on the SearchBar** (`SearchBar.tsx:73-85`) currently has no `onMicToggle` wiring on Home/Library. Wire it: clicking the mic = `voiceStart()`; second click = `voiceStop()`. (RT-hold path stays primary; the mic button is the discoverable mouse path.)

**One contentious decision:** should A on a focused input *also* dispatch into the keyboard once it opens, or should the user have to walk D-pad-down to the keyboard explicitly? **Recommendation: walk explicitly.** Auto-jumping focus mid-press is jarring and breaks the spatial-nav model the rest of the app uses.

### 5.4. Voice search activation flow

**Trigger:** held RT (or whichever the user picked in Settings).

**Visible feedback:**
1. **On RT press-down:** action footer's "RT Voice" entry pulses brief accent (0.5 s). VoiceOverlay slides in from the bottom-right (160 ms ease-out). State label reads `LISTENING`.
2. **While held:** waveform animates from microphone input. Today's `VoiceOverlay.tsx` shows `state` + `partial` + `final` text. Add a single waveform bar that animates with mic level.
3. **On RT release:** state flips to `TRANSCRIBING`. Backend posts `voice:final`.
4. **On final received:** VoiceOverlay shows the transcribed text for 5 s (`AUTO_HIDE_MS` already wired) and the text is dispatched into whatever input is focused (or, if no input is focused, opens QuickSearch with the text pre-filled).

**Error states:**
- **No model loaded.** First fix in #3 above. If the model is genuinely missing, the overlay shows `MODEL NOT INSTALLED · open Settings` with a single A-press path to Settings → Voice. **Never** show a raw error string.
- **Mic permission denied.** Show `MICROPHONE DENIED · check Windows privacy`. Single press to dismiss.
- **No audible signal.** After 1.5 s of held trigger with `level < threshold`, label flips to `STILL LISTENING…` so the user knows the trigger is held but nothing is being heard.

**Discoverability:**
- "Hold RT to speak" lives in the action footer on every page where voice is wired (everywhere).
- First-launch tour (#9) demos the trigger.

### 5.5. Tile grid couch-readability spec

**Sizes (fullscreen / `body.is-fullscreen`):**
- Tile width: `clamp(280px, 18vw, 360px)`. Today: `200px * 1.25 = 250px`. Bump.
- Tile aspect ratio: 2:3 portrait (matches Steam's `library_600x900`).
- Grid: `repeat(auto-fill, minmax(280px, 1fr))`. Today: 250 px.
- Gap: 24 px (today: 16 px). Trade column count for breathing room.
- Caption: title at `clamp(18px, 1.2vw, 22px)`. Today: `--t-title` clamps 20 → 24 px, fine. Source label at 14 px (today 12 px).

**Focus indicator (TV mode):**
- Border 4 px (today 2 px) accent-color.
- Outline offset 6 px (today implicit none).
- Scale 1.0 → 1.06 (today 1.04).
- Drop shadow `0 12px 32px color-mix(in srgb, var(--accent) 30%, transparent)` so the focused tile *floats*.
- Animation duration 200 ms (today 200 ms — keep).
- The `--ambient-art-*` background already crossfades behind the focused tile (`HomePage.tsx:178-203`). Keep this; it's the single best couch-readability feature already shipped.

**Hover (mouse) state:**
- Mirror the focus state but at 0.7 intensity (border 3 px, scale 1.04, lighter shadow). Mouse users still get feedback but the focus state remains visually dominant.

**Focus traversal:**
- The grid is not the only focusable region. Spatial nav from the grid:
  - **Up** from the top row: lands on the most recent toolbar control (search bar / sort pills / chips / Surprise Me).
  - **Down** from the bottom row: stays on the last row (no wrap; XAG 112 says 2-D grids should not loop).
  - **Left** from the leftmost column: stays.
  - **Right** from the rightmost column: stays.
- Inside a row: `data-grid-row` on every tile — `useSpatialNav` detects rows and rejects up/down candidates that have a different row index. (Today's purely-geometric algorithm sometimes lands on a tile in row N+2 instead of N+1 if N+1 is shorter.)

---

## 6. Out of scope for this wave

These came up in research and are deferred:

- **Steam-style game recording / screenshots.** Big Picture has it; we don't, and matching it requires a Tauri sidecar and storage strategy. Defer.
- **Friends / chat / social.** Pixiis is single-user. Stays that way.
- **Music playback / Spotify integration.** Big Picture has a music tab; nice-to-have but a separate epic.
- **Custom startup movies.** Pure decoration. Skip.
- **Cloud save sync across devices.** Out of scope.
- **In-game overlay (like Steam's Shift+Tab).** Requires a deep Win32 hook; not happening.
- **Per-game controller remapping** (à la Steam Input). Reuse the OS's controller drivers; we're not building Steam Input.
- **Internationalization.** Important eventually. Not this wave.
- **Theming / light mode.** Editorial palette is the brand. Don't dilute.

---

## 7. Honest priorities

If implementation has bandwidth for **three things only**, ship in this order:

1. **Wire RT to voice + fix the model default (#2 + #3).** The user's voice complaint is two stacked bugs. Fixing both makes a feature go from broken → first-class with about a day's work.
2. **Universal action footer (#1) + couch-readable focus indicator (#6).** Together these fix discoverability *and* make every existing page legible from the couch. Highest perceived improvement per LOC.
3. **Settings redesign (#4) + slider/select/hold bindings (#7).** The Settings page is the user's most-named pain. Together these make every form control reachable and adjustable from the controller.

Skip if budget is tight: **#8 (global F11), #9 (button tour), #10 (Home/Library merge).** All defensible to defer.

---

## 8. Things I think the user is wrong about

Per the brief, be opinionated.

- **"On-screen keyboard activation is broken."** It works. The mental-model mismatch (A should open it from a focused input) is real and easy to fix, but the activation policy itself is sound. Don't rip out `onInputFocus` recency check; tighten it.
- **"Bumpers don't navigate between pages."** They do (`useBumperNav.ts`). Per wave 4 final report. If the user is reporting they don't, it's likely they're inside a non-top-level route (`/game/:id`, `/files`, `/onboarding`) where bumpers intentionally no-op. The fix is the action footer telling them.
- **"Maximize button doesn't work."** It does, per wave 4 fix. If the user still sees it not work, it's a specific build/install issue, not a code bug.

These are *signals* the user wants discoverability fixed. They're not asking us to rewrite the underlying mechanics.

---

## Sources

- [Designing for Xbox and TV — Microsoft Learn](https://learn.microsoft.com/en-us/windows/apps/design/devices/designing-for-tv)
- [Xbox Accessibility Guideline 112: UI navigation](https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/112)
- [Xbox best practices — UWP applications (Microsoft Learn)](https://learn.microsoft.com/en-us/previous-versions/windows/uwp/xbox-apps/tailoring-for-xbox)
- [Steam Deck UI replaces Steam Big Picture mode on Windows PCs (PCGamesN)](https://www.pcgamesn.com/steam-deck/ui-big-picture-mode-update)
- [Big Picture Mode nobody uses or likes you (Steam Discussions)](https://steamcommunity.com/discussions/forum/0/4030223299345810473/)
- [Store Navigation is broken with Controller (Big Picture)](https://steamcommunity.com/groups/bigpicture/discussions/4/600766503721153543/)
- [Nintendo Pro controller shows wrong button prompts in Big Picture (Steam Beta)](https://steamcommunity.com/groups/SteamClientBeta/discussions/0/3185738755276274147/)
- [How to Open Keyboard on Steam Deck (Eneba)](https://www.eneba.com/hub/gaming-gear-guides/how-to-open-keyboard-on-steam-deck/)
- [Playnite Fullscreen Mode docs](https://api.playnite.link/docs/manual/gettingStarted/playniteFullscreenMode.html)
- [Playnite — Overlay to handle operations via controller (GitHub issue #3890)](https://github.com/JosefNemec/Playnite/issues/3890)
- [Plex — Android TV back button should not skip multiple levels (forum)](https://forums.plex.tv/t/android-tv-back-button-should-not-skip-multiple-levels-back-to-the-library-collection/937257)
- [Plex needs a back button on screen in TV Mode (forum)](https://forums.plex.tv/t/plex-needs-a-back-button-on-the-screen-in-tv-mode/364582)
- [Designing for tvOS — Apple HIG](https://developer.apple.com/design/human-interface-guidelines/designing-for-tvos)
- [tvOS Layout — Apple HIG](https://developer.apple.com/design/human-interface-guidelines/tvos/visual-design/layout)
- [tvOS Focus Engine (Brightec)](https://www.brightec.co.uk/blog/tvos-focus-engine)
- [Global Keyboard Shortcuts in Tauri v2 — DEV Community](https://dev.to/hiyoyok/global-keyboard-shortcuts-in-tauri-v2-the-right-way-and-the-wrong-way-2h6d)
- [Tauri Global Shortcut plugin docs](https://v2.tauri.app/plugin/global-shortcut/)
- [I stopped using my PS5 after discovering these Steam Big Picture features (MakeUseOf)](https://www.makeuseof.com/steam-big-picture-features-i-wish-id-known-about-sooner/)
