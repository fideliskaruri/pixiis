# Pane 6 — Editorial design tokens

**Branch:** `wave1/design-tokens`
**Worktree:** `/mnt/d/code/python/pixiis/.worktrees/pane6-design/`
**Wave:** 1 (Phase 1B)

> Read `/mnt/d/code/python/pixiis/agents/CONTEXT.md` first.

## Mission

Replace the existing **PS5 glass-morphism** design tokens with the new **editorial** language. Other agents will reference these tokens when building pages — your output is the foundation everyone else paints with.

## Working directory

`/mnt/d/code/python/pixiis/.worktrees/pane6-design/frontend/src/styles/`

## Reference

- Current tokens: `frontend/src/styles/theme.css` (glass-morphism, coral accents, Outfit font, springy motion). Read it; you're replacing it.
- Current animations: `frontend/src/styles/animations.css`. Same — read, replace.
- Editorial language summary is in `agents/CONTEXT.md`. Re-read the **Editorial design language** section.

## Deliverables

### 1. `frontend/src/styles/tokens.css` (new file)

```css
/* Pixiis — Editorial design tokens */

@font-face { font-family: 'Fraunces'; src: ...; font-display: swap; }
@font-face { font-family: 'Inter'; src: ...; font-display: swap; }

:root {
  /* Color */
  --bg:        #0F0E0C;          /* warm near-black */
  --bg-elev:   #15130F;          /* one notch up for cards */
  --text:      #EDE9DD;          /* off-white */
  --text-dim:  #8A8478;          /* secondary metadata */
  --text-mute: #5C574E;          /* tertiary */
  --rule:      rgba(237, 233, 221, 0.08);
  --accent:    #C5402F;          /* RESERVED for ▶ PLAY and focus rings only */
  --focus:     #C5402F;

  /* Type scale (Fraunces serif for display, Inter sans for body) */
  --font-display: 'Fraunces', 'Times New Roman', serif;
  --font-body:    'Inter', -apple-system, system-ui, sans-serif;
  --font-mono:    'IBM Plex Mono', monospace;

  /* Type sizes — fluid where it matters */
  --t-display:   clamp(48px, 6vw, 96px);
  --t-headline:  clamp(32px, 3.5vw, 56px);
  --t-title:     clamp(20px, 1.4vw, 24px);
  --t-body:      16px;
  --t-caption:   14px;
  --t-label:     12px;

  /* Letter spacing */
  --tracking-label: 0.18em;       /* small-caps tracked labels */
  --tracking-display: -0.01em;    /* tight on serif display */

  /* Spacing (4px base) */
  --s-xs: 4px;  --s-sm: 8px;  --s-md: 16px;
  --s-lg: 24px; --s-xl: 48px; --s-2xl: 96px;

  /* Motion */
  --easing: cubic-bezier(0.4, 0, 0.2, 1);
  --t-fast:   120ms;
  --t-base:   200ms;
  --t-slow:   400ms;
}

/* Small-caps tracked label primitive */
.label {
  font-family: var(--font-body);
  font-size: var(--t-label);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: var(--tracking-label);
  color: var(--text-dim);
}

/* Editorial display title */
.display {
  font-family: var(--font-display);
  font-size: var(--t-display);
  font-weight: 400;
  letter-spacing: var(--tracking-display);
  line-height: 1.05;
  color: var(--text);
}

/* Horizontal rule between magazine sections */
.rule {
  border: none;
  border-top: 1px solid var(--rule);
  margin: var(--s-xl) 0;
}

/* The single-accent button */
.accent-btn {
  background: var(--accent);
  color: var(--text);
  border: none;
  padding: var(--s-md) var(--s-xl);
  font-family: var(--font-body);
  font-size: var(--t-body);
  font-weight: 500;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: filter var(--t-base) var(--easing);
}
.accent-btn:hover { filter: brightness(1.1); }
.accent-btn:focus-visible { outline: 2px solid var(--focus); outline-offset: 4px; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  font-size: var(--t-body);
}
```

Source the **actual font files** — either embed Fraunces and Inter via `@font-face` from a CDN (Google Fonts URLs are acceptable) or download `.woff2` into `frontend/public/fonts/` and reference. Pick the cleanest approach. Both fonts are open-licensed.

### 2. `frontend/src/styles/animations.css` (replaced)

Replace contents with editorial-language animations only:
- `.fade-in` / `.fade-out` (200 ms ease-in-out) — for page transitions
- `.tile-focus` — 1px → 2px border thicken + scale 1.0 → 1.04, no spring
- `.toast-in` / `.toast-out` — 150 ms in, 300 ms out

**Delete every spring/bounce/overshoot keyframe.** The editorial language has no springs.

### 3. Update `frontend/src/index.css`

Add `@import './styles/tokens.css';` and `@import './styles/animations.css';` at the top. Don't refactor anything else in `index.css` — that's beyond your brief.

### 4. `frontend/src/styles/PALETTE.md`

A short reference doc for other agents:
- The 6 colors with hex
- The single-accent rule (only `▶ PLAY` and focus rings)
- The two-font system
- Type scale
- Spacing scale
- Motion timing

## Acceptance criteria

- `tokens.css` and `animations.css` are committed.
- `index.css` imports them.
- No JavaScript/component code changed (that's later).
- Fonts load (visible by inspecting in dev tools — but you can't run dev server in worktree without `npm install`. Skip runtime check, just verify the CSS is syntactically valid.)
- `PALETTE.md` exists for other agents.

## Out of scope

- **Don't** restyle existing components (HomePage, GameTile, etc.). Pane-6's job is the foundation, not the cleanup.
- **Don't** delete the old `theme.css` / `animations.css` files — leave them in place for the Home restyle agent to reference and remove later.

## Dependencies

- None.

## Reporting

- Update `agents/STATUS.md` when tokens are committed.
- Commit to `wave1/design-tokens`. Suggested: tokens → animations → palette.md.
