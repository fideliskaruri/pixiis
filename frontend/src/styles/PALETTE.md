# Pixiis — Editorial Palette Reference

Shared design tokens for Wave 1+ component agents. Tokens live in
`frontend/src/styles/tokens.css`; this file is a quick-reference. **Always
prefer the CSS variable over a hex literal** — that way a future palette
shift is one file, not a sweep.

## The single-accent rule

`--accent` (`#C5402F`) is reserved. Use it in exactly two places:

1. The `▶ PLAY` CTA (and the `.accent-btn` primitive).
2. `:focus-visible` outlines / focus rings (`--focus`).

Anything else — section heads, hover states, badges, links — uses
`--text` / `--text-dim` / `--text-mute`. Restraint is the design.

## Color

| Token         | Hex                     | Use                                      |
|---------------|-------------------------|------------------------------------------|
| `--bg`        | `#0F0E0C`               | Page background — warm near-black.       |
| `--bg-elev`   | `#15130F`               | One step up: cards, hover surfaces.      |
| `--text`      | `#EDE9DD`               | Primary off-white type.                  |
| `--text-dim`  | `#8A8478`               | Secondary metadata, captions.            |
| `--text-mute` | `#5C574E`               | Tertiary / disabled.                     |
| `--rule`      | `rgba(237,233,221,.08)` | Hairline rules + tile borders.           |
| `--accent`    | `#C5402F`               | `▶ PLAY` only. Also `--focus`.           |

## Typography

Two-font system. Don't introduce a third.

- **`--font-display`** — `Fraunces` (variable serif). Use for game titles,
  section heads, anything editorial-display. Pair with `--tracking-display`
  (`-0.01em`) at large sizes.
- **`--font-body`** — `Inter`. Use for body, buttons, controls, captions.
- **`--font-mono`** — `IBM Plex Mono` fallback for code/IDs only.

Both web fonts load via Google Fonts CDN with `display: swap`.

### Type scale

| Token          | Value                       | Use                                   |
|----------------|-----------------------------|---------------------------------------|
| `--t-display`  | `clamp(48px, 6vw, 96px)`    | Featured title, hero headline.        |
| `--t-headline` | `clamp(32px, 3.5vw, 56px)`  | Section heads.                        |
| `--t-title`    | `clamp(20px, 1.4vw, 24px)`  | Tile titles, dialog titles.           |
| `--t-body`     | `16px`                      | Default body.                         |
| `--t-caption`  | `14px`                      | Captions, metadata lines.             |
| `--t-label`    | `12px`                      | Small-caps labels (see `.label`).     |

### Tracked labels

Labels like `FEATURED`, `CONTINUE PLAYING`, `PLAYED` use the `.label`
primitive: Inter 500, uppercase, `letter-spacing: 0.18em`, `--text-dim`.

## Spacing (4px base)

| Token     | Value | Typical use                        |
|-----------|-------|------------------------------------|
| `--s-xs`  | 4px   | Tight icon padding.                |
| `--s-sm`  | 8px   | Inline gap, label margin.          |
| `--s-md`  | 16px  | Standard component padding.        |
| `--s-lg`  | 24px  | Card inner gap, list row spacing.  |
| `--s-xl`  | 48px  | Section padding, rule margin.      |
| `--s-2xl` | 96px  | Page gutters, hero whitespace.     |

## Motion

Editorial = restrained. **No springs. No overshoots. No bounces.**

| Token       | Value                          | Use                          |
|-------------|--------------------------------|------------------------------|
| `--easing`  | `cubic-bezier(0.4, 0, 0.2, 1)` | Default ease-in-out.         |
| `--t-fast`  | `120ms`                        | Hover state nudges.          |
| `--t-base`  | `200ms`                        | Page cross-fade, tile focus. |
| `--t-slow`  | `400ms`                        | Larger view transitions.     |

Animations live in `animations.css`:

- `.fade-in` / `.fade-out` — page cross-fade.
- `.tile-focus` — 1px → 2px border + scale 1.0 → 1.04, no spring.
- `.toast-in` (150ms) / `.toast-out` (300ms) — asymmetric for legibility.
- All collapse to ~1ms under `prefers-reduced-motion: reduce`.

## Primitives shipped today

- `.label` — small-caps tracked label.
- `.display` — Fraunces editorial title.
- `.rule` — `<hr>` styled as the section divider.
- `.accent-btn` — the `▶ PLAY` button.

## Notes for component agents

- `theme.css` (PS5 glass) is still on disk for now — the Home restyle
  agent will sweep it. New code should not import it.
- If you need a new color or scale step, add a token here first; don't
  inline a hex.
