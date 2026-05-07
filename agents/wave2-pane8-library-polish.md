# Wave 2 Pane 8 — Library + GameDetail polish

**Branch:** `wave2/library-polish`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/wave2-library-polish/`

> Read `agents/CONTEXT_WAVE2.md` first.

## Mission

The integration agent already shipped Library + GameDetail at "iteration 3.5 — apply reviewer findings". Your job: **review against the editorial wireframe**, identify gaps, and tighten. No major rewrites.

## Reference

- Existing files (your starting point — read these first):
  - `src/pages/LibraryPage.tsx`, `LibraryPage.css`
  - `src/pages/GameDetailPage.tsx`, `GameDetailPage.css`
- Wireframes (re-read): the magazine layout established in earlier conversation — featured slot, small-caps section labels, horizontal rules, single accent for ▶ PLAY
- Tokens: `src/styles/PALETTE.md`
- Wave 1 inventory of behaviors to preserve: `agents/STATUS.md` (search "behavior inventory")

## Things to review and tighten

1. **Single-accent rule:** the only saturated `var(--accent)` should be the ▶ PLAY button and focus rings. Anywhere else accent is leaking → change to `var(--text)` or `var(--text-dim)`.
2. **Type hierarchy:** game titles use Fraunces display, body uses Inter, small-caps tracked labels for `FEATURED`, `CONTINUE PLAYING`, `PLAYED`, `LAST`, `RATING`, `STORE`, etc.
3. **Horizontal rules:** between magazine sections (`<hr class="rule">` or equivalent). 1 px `var(--rule)`, generous margin.
4. **Featured slot (Library):** if Library has a featured slot, ensure asymmetric layout (art ~60%, prose ~40%). If it doesn't, decide whether to add one — it's a Library page, the value of a featured slot is debatable. Default to omitting.
5. **GameDetail layout:** hero image full-bleed at top, title overlaid in display serif. Below: small-caps metadata strip → ▶ PLAY (the single accent on the page) → metadata sidebar (PLAYED, LAST, RATING, STORE, SIZE, GENRE) on left + body description on right → SCREENSHOTS rail → STREAMING NOW + VIDEOS columns.
6. **Motion:** verify only cross-fades, no springs/bounces. Hunt down any `transition: transform ... cubic-bezier(... overshoot)` or Framer Motion `spring` configs and replace with `ease-in-out` 200 ms.
7. **Focus rings:** every focusable element shows a `2px solid var(--focus)` ring with 4 px offset on `:focus-visible`. Test by tabbing through the page.
8. **Empty states:** when Library is empty (no games), show a magazine-style empty state — quiet serif heading, small-caps body, no decorative icon.
9. **Spatial nav:** verify Library tile grid responds to `useSpatialNav` and the tab order matches reading order.

## Deliverables

- A short **review report** at `agents/wave2-pane8-review.md` listing what you found and what you changed
- Edits to `LibraryPage.tsx/.css` and `GameDetailPage.tsx/.css` for the gaps
- Optionally: extract any repeated primitives (`<SmallCapsLabel>`, `<Rule>`, `<MetadataRow>`) into `src/components/` if they'd help downstream pages (Settings/Onboarding/Files)

## Acceptance criteria

- Single-accent rule holds
- Tab order is sane
- No springs
- Empty states render in editorial style
- Pages still pass any existing tests / typecheck

## Out of scope

- Major restructure (you're polishing, not rebuilding)
- Adding new features
- New pages — those are Panes 5/6/7

## Reporting

Append to `agents/STATUS.md`. Commit to `wave2/library-polish`. The review report is part of the deliverable, commit it too.
