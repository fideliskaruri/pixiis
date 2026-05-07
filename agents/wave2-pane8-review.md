# Wave 2 Pane 8 — Library + GameDetail polish review

Branch: `wave2/library-polish`
Reviewed against the brief at `agents/wave2-pane8-library-polish.md`
and the editorial wireframe established in earlier conversation.

> Note on file layout. The brief refers to `LibraryPage.tsx/.css`, but in
> this repo the Library lives in `src/pages/HomePage.tsx/.css` (HomePage
> is the library grid + Continue Playing band). Polished those.

## Scope

Audit + tighten of:

- `src/pages/HomePage.tsx` / `HomePage.css` (Library)
- `src/pages/GameDetailPage.tsx` / `GameDetailPage.css` (Detail)
- The shared GameTile / SearchBar / NavBar are *touched only as evidence*
  for the audit; not edited (those belong to other panes).

## What was already in good shape

| Item | Evidence |
|---|---|
| Single-accent rule | Only `.accent-btn` consumes `var(--accent)` (in `tokens.css`). Active source (`HomePage.css`, `GameDetailPage.css`, `GameTile.css`, `NavBar.css`, `SearchBar.css`) references the accent only via `var(--focus)` — same hex, but reads as a focus ring everywhere else. `theme.css` (legacy PS5-glass tokens) still defines `--accent: #e94560` but is not imported (`App.tsx` comment confirms). |
| Type hierarchy | Game titles use `.display` (Fraunces). Body uses Inter (`var(--font-body)`). Small-caps tracked labels (`CONTINUE PLAYING`, `LIBRARY`, `STEAM`, `PLAYED`, `RATING`, `STORE`, `ABOUT`, `SCREENSHOTS`) all render via the `.label` primitive. |
| Horizontal rules | `<hr class="rule">` after Continue Playing, `border-bottom: 1px solid var(--rule)` under the Library toolbar, `border-top: 1px solid var(--rule)` between Detail meta-body / about / screenshots. |
| Motion | Every transition routes through `var(--easing)` = `cubic-bezier(0.4, 0, 0.2, 1)` (ease-in-out). No springs, no overshoots. `framer-motion` is in `package.json` but not imported in active code. The legacy `--ease-spring` is in `theme.css` only, which is unused. |
| Spatial nav | `useSpatialNav` finds the nearest focusable in the pressed direction; tile grid + carousel both have `data-focusable`. Keyboard tab order matches reading order (Continue Playing → toolbar → sort pills → grid → tile detail). |

## Gaps found and fixed

### 1. GameDetail hero — full-bleed banner with title overlay

The integration version rendered the hero as a 2:3 portrait poster capped
at 720 px wide. The wireframe calls for "hero image full-bleed at top,
title overlaid in display serif". Reworked to two modes:

- **Banner** — used when RAWG returned `background_image`. 21:9, full
  content-width, `.detail__hero-overlay` places source label + display
  title at the bottom-left over the existing `.detail__hero-fade` scrim.
- **Poster** — used when no banner is available. 2:3, capped at 480 px,
  title rendered below in a `.detail__header`. The wireframe overlay
  doesn't work on portrait poster art (the title bar sits in the middle
  of the artwork), so we keep the title-below treatment in this case.

Files: `GameDetailPage.tsx` (heroMode picker, conditional overlay),
`GameDetailPage.css` (`.detail__hero--banner`, `.detail__hero--poster`,
`.detail__hero-overlay`, taller `.detail__hero-fade` scrim).

### 2. Two-column body — meta sidebar + about

The integration version placed metadata as a horizontal strip above the
actions, and the about description as a single column below. The
wireframe calls for "metadata sidebar (PLAYED, LAST, RATING, STORE,
SIZE, GENRE) on left + body description on right". Reworked into a
`.detail__body` two-column grid:

- **Sidebar** (left, `minmax(200px, 280px)`): the meta `<dl>` plus a
  `GENRE` block. Rows rendered: `PLAYED`, `RATING`, `RELEASED`, `STORE`,
  and `STATUS: Not installed` when applicable. `LAST` and `SIZE` are
  omitted because the data model doesn't surface them (last_played is
  an epoch on `AppEntry` but no relative-date formatter is in scope;
  install size isn't tracked at all).
- **About** (right, `minmax(0, 1fr)`, capped at 720 px for line length):
  the description, paragraph-split. When RAWG hasn't returned anything
  (or returned an empty description), shows a quiet
  "Description not available." in `--text-dim` instead of disappearing.

Below 720 px the grid collapses to one column.

Files: `GameDetailPage.tsx` (new `<div class="detail__body">` wrapper),
`GameDetailPage.css` (`.detail__body`, `.detail__sidebar`,
`.detail__sidebar-block`; `.detail__meta` now vertical flex rather
than auto-fit grid; genre list now stacked vertically).

### 3. Source label — strip vs overlay

Was rendered inside the meta `<dl>` as just a top-line. Promoted to a
proper "small-caps metadata strip" — overlaid on the hero in banner
mode, in `.detail__header` above the title in poster mode. Sidebar
keeps a separate `STORE` row since the wireframe explicitly calls for
that even when the strip and store value are identical.

### 4. Focus rings standardized at 4 px offset (Library + Detail)

The `.accent-btn` primitive in `tokens.css` was already at the spec'd
4 px offset; the rest of Library + Detail were at 2 px. Bumped:

- `home__pill:focus-visible` 2 → 4
- `home__retry:focus-visible` 2 → 4
- `detail__favorite:focus-visible` 2 → 4
- `detail__screen:focus-visible` 2 → 4
- `detail__back:focus-visible` was using a `border-color` swap with
  `outline: none`; replaced with the standard `outline: 2px solid
  var(--focus); outline-offset: 4px`.

NavBar / SearchBar were left at 2 px — those are shared chrome
components, out of polish scope. Documented under deferred below.

### 5. Library empty state — quieter heading

Empty-state title was using the `.display` class (`--t-display`,
clamp 48–96 px). At that size it reads as a hero, not as a quiet
magazine empty state. Replaced with a scoped style that still uses
Fraunces and `--tracking-display`, but at `--t-headline` (32–56 px) so
"No games yet", "One moment.", and "Failed to load library" feel like
calm editorial pull-quotes rather than featured-art display titles.

Files: `HomePage.tsx` (drop the `.display` class), `HomePage.css`
(scoped `.home__empty-title` rule).

## Acceptance criteria

| Criterion | Status |
|---|---|
| Single-accent rule holds | Verified — see "What was already in good shape" |
| Tab order is sane | Verified — DOM reading order |
| No springs | Verified — only `var(--easing)` ease-in-out, no spring/overshoot beziers, no Framer Motion in active code |
| Empty states render in editorial style | Fixed — quieted to `--t-headline` |
| Pages still typecheck | TypeScript not runnable in this WSL (no installed `tsc`); JSX hand-verified for clean prop/import shape — only modified imports/usages where needed (`imageUrl` still used for poster fallback). |

## Deferred / out of scope

- **STREAMING NOW + VIDEOS columns on GameDetail.** Backend has
  `services_twitch_streams` + `services_youtube_trailer` from Wave 1, but
  neither is wired through `bridge.ts`, and `RawgGameData` doesn't
  surface either. Adding these is feature wiring, not polish. Flagged
  for a follow-up wave.
- **Library featured slot.** Brief says "decide whether to add one … 
  default to omitting." Default kept — Library is a single grid plus the
  Continue Playing carousel, which already gives the page asymmetry.
- **`theme.css` legacy tokens.** Still on disk, no longer imported from
  any active module. Safe to delete in a future sweep but out of polish
  scope here.
- **NavBar / SearchBar focus-ring offsets.** Both shared chrome
  components. Bumping to 4 px without coordinating with Pane 0
  (chrome-fix) risks visual collision in tightly-packed regions. Kept
  at 2 px; consistency-with-the-rest can be a one-line follow-up.
- **`<SmallCapsLabel>` / `<Rule>` / `<MetadataRow>` extractions.** Brief
  lists these as optional. The CSS primitives (`.label`, `.rule`,
  `.detail__meta-row`) are doing the work; pre-extracting React
  components on speculation would invert the dependency between Pane 8
  and the still-unwritten Settings/Onboarding/Files panes. Better for
  whichever pane reaches for the second copy to extract at that point.

## Files changed

- `src/pages/HomePage.tsx` — drop `.display` from empty-state titles
- `src/pages/HomePage.css` — scoped `.home__empty-title`, focus offsets to 4 px
- `src/pages/GameDetailPage.tsx` — heroMode picker, banner overlay, two-column body, sidebar meta, conditional about
- `src/pages/GameDetailPage.css` — `.detail__hero--banner|--poster`, `.detail__hero-overlay`, `.detail__body`, `.detail__sidebar`, vertical meta, vertical genres, focus offsets to 4 px
- `agents/wave2-pane8-review.md` — this file
- `agents/STATUS.md` — start + done entries
