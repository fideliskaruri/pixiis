# Pixiis Design Specification v2.0

> A comprehensive visual identity guide for the Pixiis game launcher.
> Every value is implementation-ready. The implementation agent should follow this spec exactly.

---

## Design Philosophy

Pixiis should feel like a **cinematic living room** — warm, inviting, and focused entirely on your games. Not a storefront. Not a social feed. A personal collection rendered with care.

**Core principles:**
1. **Content is king** — game art is the hero element; chrome recedes
2. **Warm darkness** — not cold blue-black; a rich, plum-touched darkness that feels inviting
3. **Atmospheric accent** — the coral accent breathes through the UI as subtle ambient light
4. **Effortless navigation** — controller users never wonder "where am I?"
5. **Quiet luxury** — premium feel through restraint, not decoration

**Inspirations synthesized (not copied):**
- PS5: Content-forward cards, atmospheric backgrounds, smooth focus transitions
- Steam Deck: Large touch targets, clear D-pad navigation, controller-first everything
- Xbox Series X: Depth layers, accent color flexibility, clean grid layouts
- Apple TV: Typography hierarchy, generous whitespace, cinematic presentation
- Plex: Media library polish, warm dark theme, content density balance

---

## 1. Color System

### Core Palette

| Token | Hex | RGB | Usage |
|---|---|---|---|
| `background` | `#0b0a10` | `11, 10, 16` | App background, deepest layer |
| `surface` | `#13121a` | `19, 18, 26` | Cards, panels, primary surfaces |
| `surface_elevated` | `#1c1a24` | `28, 26, 36` | Modals, dropdowns, floating elements |
| `surface_hover` | `#252330` | `37, 35, 48` | Hover state for surfaces |
| `accent` | `#e94560` | `233, 69, 96` | Primary action color, focus rings, brand |
| `accent_hover` | `#ff5a78` | `255, 90, 120` | Accent hover/active state |
| `accent_pressed` | `#c93a52` | `201, 58, 82` | Accent pressed state |
| `text_primary` | `#f0eef5` | `240, 238, 245` | Headings, primary labels |
| `text_secondary` | `#8a8698` | `138, 134, 152` | Body text, descriptions |
| `text_muted` | `#5c586a` | `92, 88, 106` | Hints, disabled text, timestamps |
| `success` | `#4ade80` | `74, 222, 128` | Install complete, ready state |
| `warning` | `#fbbf24` | `251, 191, 36` | Installing, updates available |
| `error` | `#ef4444` | `239, 68, 68` | Failed, error states |
| `border` | `rgba(255, 255, 255, 0.06)` | — | Subtle dividers, card edges |
| `border_hover` | `rgba(255, 255, 255, 0.12)` | — | Hover-state borders |

### Computed Variants (generated in ThemeManager)

| Token | Derivation | Usage |
|---|---|---|
| `accent_dim` | `rgba(233, 69, 96, 0.10)` | Very subtle tints, active nav background |
| `accent_glow` | `rgba(233, 69, 96, 0.30)` | Focus glow, hover border tint |
| `accent_atmospheric` | `rgba(233, 69, 96, 0.05)` | Faint background warmth wash |
| `surface_border` | `rgba(255, 255, 255, 0.06)` | Default card/panel borders |
| `shadow_color` | `rgba(0, 0, 0, 0.40)` | Drop shadows on elevated elements |

### Color Rationale

**Why warm plum-blacks instead of cold blue-blacks:**
The previous `#08080c` / `#0f0f15` / `#161620` palette had a cold, technical feel. The new `#0b0a10` / `#13121a` / `#1c1a24` progression introduces a subtle warm plum undertone (the blue channel is slightly higher than green, but both are warmer than pure blue-black). This creates a surface that feels like a dimmed theater — inviting, not sterile.

**Why `#e94560` accent stays:**
This coral-crimson is distinctive. It's not boring blue (Steam, Discord), not generic red (Netflix error-red), not neon green (Xbox, Razer). It's warm, energetic, and instantly recognizable as Pixiis. It also has excellent contrast against dark backgrounds (WCAG AA compliant for text at all sizes on `#0b0a10`).

---

## 2. Typography

### Font Stack

```
Primary: "Segoe UI Variable", "Segoe UI", "Inter", "SF Pro Display", system-ui, sans-serif
Monospace: "Cascadia Code", "JetBrains Mono", "Consolas", monospace
```

Segoe UI is native on Windows (the primary platform). Inter is the fallback for Linux/cross-platform.

### Type Scale

| Level | Size | Weight | Letter-spacing | Line-height | Usage |
|---|---|---|---|---|---|
| **Display** | 32px | Bold (700) | -0.03em | 1.1 | Hero game title on detail page |
| **H1** | 24px | Bold (700) | -0.02em | 1.2 | Page titles ("Library", "Settings") |
| **H2** | 20px | SemiBold (600) | -0.01em | 1.25 | Section headers |
| **H3** | 16px | SemiBold (600) | 0 | 1.3 | Sub-section headers, card titles |
| **Body** | 14px | Regular (400) | 0 | 1.5 | General text, descriptions |
| **Body Small** | 13px | Regular (400) | 0 | 1.4 | Secondary information |
| **Caption** | 12px | Medium (500) | 0.01em | 1.3 | Metadata, timestamps |
| **Badge** | 10px | Bold (700) | 0.06em | 1.0 | Source badges, tags, pills |
| **Overline** | 11px | SemiBold (600) | 0.08em | 1.0 | Category labels (all-caps) |

### Typography Rules

- **Headings** are always `text_primary` (`#f0eef5`)
- **Body text** uses `text_secondary` (`#8a8698`) — this creates natural hierarchy without needing many font sizes
- **Interactive labels** (buttons, nav items) use `text_primary` when active, `text_secondary` when inactive
- **Never use pure white** (`#ffffff`) for text — it's too harsh on dark backgrounds
- **Game titles on tiles** use H3 (16px SemiBold) with `text_primary`
- Title text on tiles should be truncated with ellipsis after 2 lines max

---

## 3. Spacing System

### Base Unit: 4px

All spacing values are multiples of 4px. This creates a harmonious rhythm.

| Token | Value | Usage |
|---|---|---|
| `space_xs` | 4px | Icon padding, tight internal gaps |
| `space_sm` | 8px | Between related inline elements, small gaps |
| `space_md` | 12px | Default element spacing, list item padding |
| `space_lg` | 16px | Card internal padding, section gaps |
| `space_xl` | 24px | Between sections, tile grid gaps |
| `space_2xl` | 32px | Major section breaks, page top padding |
| `space_3xl` | 48px | Page side margins, hero spacing |

### Layout Grid

- **Page side margins**: 32px left/right (shrink to 24px on narrow windows)
- **Page top padding**: 24px below the navbar
- **Tile grid gap**: 20px horizontal, 20px vertical (tightened from 24px for better density)
- **Section vertical spacing**: 24px between search bar and tiles, 32px between major sections
- **Card internal padding**: 16px all sides for content cards; 0 for game tiles (image bleeds to edge)

---

## 4. Card / Game Tile Design

### Dimensions

| Property | Value | Notes |
|---|---|---|
| **Width** | 220px | Slightly smaller for better density — fits 5 tiles at 1280px |
| **Height** | 308px | Maintains 5:7 portrait ratio |
| **Corner Radius** | 10px | Softer than 14px, more refined |
| **Border** | 1px solid `border` | `rgba(255,255,255,0.06)` — barely visible, adds definition |
| **Background** | `surface` | `#13121a` shown when no image loaded |

### Visual Layers (painted in order)

1. **Image** — center-cropped to fill tile, clipped to rounded rect
2. **Bottom gradient** — `linear-gradient(transparent 50%, rgba(0,0,0,0.85) 100%)` — ensures text legibility
3. **Game name** — positioned 12px from bottom, 12px horizontal padding, max 2 lines
4. **Source badge** — top-right corner, 6px from edges

### Tile States

**Default (idle):**
```
border: 1px solid rgba(255, 255, 255, 0.06)
transform: scale(1.0)
shadow: none
```

**Hovered (mouse):**
```
border: 1px solid rgba(233, 69, 96, 0.25)
brightness overlay: +3% white overlay
transition: 180ms ease-out
```

**Focused (D-pad / keyboard):**
```
border: 2px solid #e94560
outer glow: 0 0 12px rgba(233, 69, 96, 0.35)
transform: scale(1.03)
transition: 200ms ease-out
```
The focus state MUST be significantly more prominent than hover — controller users rely on it exclusively.

**Pressed (A button / Enter / click):**
```
transform: scale(0.98)
border: 2px solid #ff5a78
transition: 80ms ease-in
```

### Source Badge

```
position: top-right, 8px from top, 8px from right
background: rgba(0, 0, 0, 0.65)
backdrop-blur: (not available in Qt — use solid dark bg)
border-radius: 4px
padding: 3px 6px
font: Badge level (10px Bold, 0.06em tracking, uppercase)
color: text_secondary (#8a8698)
```

Labels: `STEAM`, `XBOX`, `PC`, `CUSTOM`, `GOG`, `EPIC`

### Tile Grid Arrangement

- **Layout**: FlowLayout (wrapping) — tiles flow left-to-right, wrap to next row
- **Horizontal gap**: 20px
- **Vertical gap**: 20px
- **Alignment**: left-aligned rows (no centering — consistent left edge)
- **Minimum tiles per row**: 3 (at minimum window width 1280px minus margins)
- **Scroll**: Vertical smooth scroll, scroll bar hidden by default, thin 6px bar on scroll

### Placeholder (no image)

When a game has no cover art:
```
background: linear-gradient(135deg, surface_elevated 0%, surface 100%)
center icon: game controller silhouette, 48px, text_muted color
below icon: game name in H3, text_secondary, centered
```

---

## 5. Navigation Bar (Sidebar)

### Dimensions

| Property | Value |
|---|---|
| **Height** | 52px (reduced from 60px — less chrome, more content) |
| **Background** | `#0e0d14` (between background and surface — its own distinct layer) |
| **Bottom border** | 1px solid `rgba(255, 255, 255, 0.04)` — barely there separator |
| **Horizontal padding** | 16px left, 8px right |

### Layout

```
[LOGO 16px] [24px gap] [Home] [Library] [Settings] [Files] [stretch] [_ □ X]
```

### Logo

```
text: "PIXIIS"
font: 18px, Bold (700), letter-spacing: 0.12em
color: #e94560 (accent)
```

The logo is text-only — no icon. The wide letter-spacing gives it a premium, minimalist feel. All caps.

### Nav Items

```
font: 13px, Medium (500)
color (inactive): text_secondary (#8a8698)
color (active): text_primary (#f0eef5)
color (hover): text_primary (#f0eef5)
padding: 8px 14px
border-radius: 6px
```

**Active indicator:** A 2px-tall accent bar at the bottom of the nav item, with 2px border-radius on top corners. The bar extends the full width of the text + padding.

```
active bar: 2px height, background #e94560, bottom-aligned
active background: rgba(233, 69, 96, 0.08) — very faint tint
```

### Nav Focus State (controller)

When navigating the nav bar with D-pad:
```
background: rgba(233, 69, 96, 0.12)
border: 1px solid rgba(233, 69, 96, 0.30)
border-radius: 6px
text color: text_primary
transition: 150ms
```

### Window Controls (minimize, maximize, close)

```
size: 32x32px
icon size: 14px (drawn with lines, not images)
color: text_muted (#5c586a)
hover background: surface_hover (#252330)
hover color: text_secondary (#8a8698)
close hover: background #e94560, icon color #ffffff
border-radius: 6px
spacing: 2px between buttons
```

---

## 6. Focus States (Critical for Controller)

### Universal Focus Ring

Every focusable element MUST have a visible focus indicator. The system uses a **two-tier approach**:

#### Tier 1: Bordered elements (tiles, cards, inputs, buttons)
```
border: 2px solid #e94560
box-glow: 0 0 8px rgba(233, 69, 96, 0.30)   (QGraphicsDropShadowEffect)
transition: 200ms OutCubic
```

#### Tier 2: Text/inline elements (nav items, pills, links)
```
background: rgba(233, 69, 96, 0.12)
border: 1px solid rgba(233, 69, 96, 0.30)
border-radius: 6px
transition: 150ms OutCubic
```

### Per-Component Focus Specs

| Component | Focus Treatment |
|---|---|
| **Game Tile** | 2px accent border + outer glow (12px spread, 35% opacity) + scale(1.03) |
| **Search Bar** | 2px accent border + subtle bottom glow + accent placeholder icon |
| **Nav Button** | Background tint + accent border + text becomes `text_primary` |
| **Sort/Filter Pill** | Background tint + accent border |
| **Settings Control** | 2px accent border on the input/slider/toggle |
| **Action Button** | If primary: brighten to `accent_hover`. If secondary: add accent border |
| **Scroll Area** | When focused, scrollbar handle turns accent color |

### Focus Navigation Order

The focus order follows a natural reading pattern:
1. Search bar (top of page)
2. Sort/filter pills (below search)
3. Game tiles (grid, left-to-right, top-to-bottom)
4. Nav bar is accessible via LB/RB shoulder buttons, not D-pad from content area

### Focus Memory

When returning to a page, focus should restore to the last-focused element on that page.

---

## 7. Buttons

### Primary Button (accent-filled)

```
background: linear-gradient(180deg, #e94560 0%, #c93a52 100%)
color: #ffffff
font: 14px SemiBold (600)
padding: 10px 20px
border: none
border-radius: 8px
hover: background shifts to linear-gradient(180deg, #ff5a78 0%, #e94560 100%)
pressed: background #c93a52 solid, scale(0.97)
focus: outer glow 0 0 8px rgba(233,69,96,0.35)
disabled: opacity 0.4, no hover/press
```

### Secondary Button (outlined)

```
background: transparent
color: text_primary (#f0eef5)
font: 14px Medium (500)
padding: 10px 20px
border: 1px solid rgba(255, 255, 255, 0.12)
border-radius: 8px
hover: border-color rgba(233, 69, 96, 0.30), background rgba(233, 69, 96, 0.06)
pressed: background rgba(233, 69, 96, 0.12)
focus: border 2px solid #e94560
disabled: opacity 0.4
```

### Ghost Button (text-only)

```
background: transparent
color: text_secondary (#8a8698)
font: 14px Regular (400)
padding: 8px 12px
border: none
hover: color text_primary, background rgba(255,255,255,0.04)
pressed: background rgba(255,255,255,0.06)
focus: background rgba(233,69,96,0.08), color accent
```

### Pill Button (sort/filter toggles)

```
background (inactive): surface (#13121a)
background (active): rgba(233, 69, 96, 0.15)
color (inactive): text_secondary
color (active): #e94560
font: Caption (12px Medium)
padding: 6px 14px
border: 1px solid border (inactive) / rgba(233,69,96,0.30) (active)
border-radius: 16px (full pill)
```

---

## 8. Search Bar

### Dimensions

```
height: 44px
border-radius: 22px (full pill)
background: surface (#13121a)
border: 1px solid rgba(255, 255, 255, 0.06)
padding: 0 16px 0 44px (space for search icon on left)
```

### Search Icon

```
position: 16px from left, vertically centered
size: 16px
color: text_muted (#5c586a)
focused color: accent (#e94560)
```

### Text

```
font: 14px Regular (400)
color: text_primary (#f0eef5)
placeholder: "Search games..." in text_muted (#5c586a)
```

### States

```
hover: border-color rgba(255, 255, 255, 0.12)
focus: border 2px solid #e94560, subtle bottom glow, search icon turns accent
```

---

## 9. Page Layouts

### Home Page

```
┌──────────────────────────────────────────────────────────┐
│  PIXIIS   [Home] [Library] [Settings] [Files]    [_ □ X]│  ← 52px navbar
├──────────────────────────────────────────────────────────┤
│  32px padding                                            │
│  ┌─[🔍 Search games...]──────────────┐  [A-Z ▾] [Recent]│  ← search + sort pills
│  └───────────────────────────────────┘                   │
│  24px gap                                                │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │  ← game tile grid
│  │     │ │     │ │     │ │     │ │     │              │     220x308 tiles
│  │     │ │     │ │     │ │     │ │     │              │     20px gaps
│  │ Art │ │ Art │ │ Art │ │ Art │ │ Art │              │
│  │     │ │     │ │     │ │     │ │     │              │
│  │Name │ │Name │ │Name │ │Name │ │Name │              │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘              │
│  ┌─────┐ ┌─────┐ ┌─────┐ ...                           │
│  │     │ │     │ │     │                                │
│  └─────┘ └─────┘ └─────┘                                │
└──────────────────────────────────────────────────────────┘
```

- Search bar stretches to fill available width minus pill buttons
- Pills float to the right of search on the same row
- Tile grid fills remaining vertical space with smooth vertical scroll
- First tile auto-focused on page load (for controller users)
- Game count shown in `text_muted` below search row: "127 games"

### Game Detail Page

```
┌──────────────────────────────────────────────────────────┐
│  ← Back                                         [_ □ X] │  ← navbar with back
├──────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐    │
│  │                                                  │    │  ← hero image area
│  │            (blurred game art background)         │    │     240px height
│  │                                                  │    │     gradient fade
│  │  ┌──────┐                                        │    │     to background
│  │  │Cover │  GAME TITLE (Display: 32px Bold)       │    │
│  │  │ Art  │  Source badge   |   Genre tags          │    │
│  │  │120x168│                                       │    │
│  │  └──────┘  [▶ Launch]  [⚙ Settings]              │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
│  About                                                   │  ← section header H2
│  Lorem ipsum description text in body/text_secondary...  │
│                                                          │
│  Details                                                 │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐          │  ← info cards
│  │ Install    │ │ Last Played│ │ Play Time  │          │     surface bg
│  │ Location   │ │ 2 days ago │ │ 42 hours   │          │
│  └────────────┘ └────────────┘ └────────────┘          │
└──────────────────────────────────────────────────────────┘
```

- Hero area: 240px tall, blurred game art as background, gradient fade to page background at bottom
- Cover art: 120x168px thumbnail (same 5:7 ratio as tiles)
- Launch button: Primary button style, prominently placed
- Info cards: `surface_elevated` background, 12px border-radius, 16px padding

### Settings Page

```
┌──────────────────────────────────────────────────────────┐
│  PIXIIS   [Home] [Library] [Settings] [Files]    [_ □ X]│
├──────────────────────────────────────────────────────────┤
│  32px padding                                            │
│  Settings (H1)                                           │
│                                                          │
│  ┌─ Appearance ──────────────────────────────────────┐   │  ← GroupBox
│  │  Theme          [Dark ▾]                          │   │     surface bg
│  │  Accent Color   [● ● ● ● ● ●]  [Custom...]      │   │     12px radius
│  │  Font Size      [────●────────]  14px             │   │     16px padding
│  └───────────────────────────────────────────────────┘   │
│  24px gap                                                │
│  ┌─ Game Sources ────────────────────────────────────┐   │
│  │  Steam          [✓ Enabled]      [Scan Now]       │   │
│  │  Xbox           [✓ Enabled]      [Scan Now]       │   │
│  │  Custom Folders [+ Add Folder]                    │   │
│  └───────────────────────────────────────────────────┘   │
│  24px gap                                                │
│  ┌─ Controller ──────────────────────────────────────┐   │
│  │  Vibration      [────●────────]  70%              │   │
│  │  Dead Zone      [──●──────────]  0.4              │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

- Scrollable page with grouped sections
- GroupBox: `surface` background, 1px `border`, 12px border-radius
- GroupBox header: H3, text_primary, 16px bottom margin
- Form rows: label left-aligned, control right-aligned, 48px row height
- Sliders: track in `surface_elevated`, handle in `accent`, 16px handle diameter
- Toggles: pill-shaped, 40x22px, `accent` when on, `surface_elevated` when off
- Dropdowns: `surface` background, `border`, 8px border-radius

---

## 10. Scroll Bars

```
width: 6px
track: transparent (invisible track)
handle: rgba(255, 255, 255, 0.10)
handle hover: rgba(255, 255, 255, 0.20)
handle radius: 3px (full round)
margin: 2px from right edge
```

Scroll bars should **fade in on scroll** and **fade out after 1.5s of inactivity**. When a scroll area has focus (controller), the handle turns `accent` at 40% opacity.

---

## 11. Animations

### Timing Tokens

| Token | Duration | Easing | Usage |
|---|---|---|---|
| `instant` | 0ms | — | Immediate state changes (active → pressed) |
| `fast` | 100ms | OutCubic | Button press feedback, pill toggle |
| `normal` | 180ms | OutCubic | Hover in/out, border color changes |
| `smooth` | 250ms | OutCubic | Page transitions, panel slides |
| `gentle` | 350ms | OutCubic | Scroll-to-tile, content fade-in |
| `slow` | 500ms | InOutCubic | Fade overlays, modal appear/dismiss |

### What Animates

| Element | Trigger | What Changes | Timing |
|---|---|---|---|
| Game Tile | hover in | border-color, brightness overlay | `normal` (180ms) |
| Game Tile | hover out | border-color, brightness overlay | `normal` (180ms) |
| Game Tile | focus in | border, glow, scale(1.03) | `normal` (180ms) |
| Game Tile | focus out | border, glow, scale(1.0) | `normal` (180ms) |
| Game Tile | pressed | scale(0.98) | `fast` (100ms) |
| Search Bar | focus in | border-color, icon color | `normal` (180ms) |
| Nav Item | hover/focus | background-color, text color | `fast` (100ms) |
| Page Stack | page change | slide left/right | `smooth` (250ms) |
| Scroll | tile focus | scroll position | `gentle` (350ms) |
| Tile Image | loaded | opacity 0→1 | `slow` (500ms) |

### What Does NOT Animate

- Text color changes on state toggle (instant)
- Badge appearances (instant)
- Checkbox/toggle value changes (instant snap, no slide)
- Window resize (instant relayout)
- First paint (no entrance animations — app should feel "already there")

### QPropertyAnimation Implementation Notes

Since QSS has NO transition support, all animations must be done via `QPropertyAnimation`:
- Use `QEasingCurve.OutCubic` for most transitions (fast start, gentle land)
- Use `QEasingCurve.InOutCubic` for symmetrical animations (pulsing, looping)
- Always call `.stop()` on running animations before starting new ones
- Properties must use `@Property(type)` decorator with setter calling `self.update()`
- Scale animations require custom `paintEvent` with `QTransform`
- Glow effects use `QGraphicsDropShadowEffect` with animated color/blur properties

---

## 12. Inputs & Form Controls

### Text Input (QLineEdit)

```
height: 40px
background: surface (#13121a)
border: 1px solid border
border-radius: 8px
padding: 0 12px
font: Body (14px Regular)
color: text_primary
placeholder color: text_muted
hover: border-color border_hover
focus: border 2px solid accent
```

### Slider (QSlider)

```
track height: 4px
track background: surface_elevated (#1c1a24)
track border-radius: 2px
filled track: accent (#e94560)
handle: 16px circle, accent, 1px white border at 10% opacity
handle hover: 18px circle (slight grow)
handle focus: 18px circle + outer glow
```

### Toggle (custom QCheckBox)

```
width: 40px, height: 22px
off: surface_elevated background, border rgba(255,255,255,0.10)
on: accent background
knob: 18px white circle, 2px from edge
border-radius: 11px (full pill)
transition: 180ms
```

### Dropdown (QComboBox)

```
height: 40px
background: surface
border: 1px solid border
border-radius: 8px
padding: 0 12px
dropdown arrow: text_muted, 10px
popup: surface_elevated, border, 8px radius, 4px shadow
popup item height: 36px
popup item hover: surface_hover
popup item selected: accent_dim background, accent text
```

---

## 13. Shadows & Depth

QSS doesn't support box-shadow. Use `QGraphicsDropShadowEffect` in code.

### Shadow Levels

| Level | Blur | Offset Y | Color | Usage |
|---|---|---|---|---|
| **sm** | 4px | 2px | `rgba(0,0,0,0.20)` | Subtle card lift |
| **md** | 8px | 4px | `rgba(0,0,0,0.30)` | Elevated surfaces, dropdowns |
| **lg** | 16px | 8px | `rgba(0,0,0,0.40)` | Modals, floating panels |
| **glow** | 12px | 0px | `rgba(233,69,96,0.30)` | Focused game tiles, accent glow |

### Depth Hierarchy

```
Layer 0 (deepest):  background  #0b0a10   — app background
Layer 1:            surface     #13121a   — cards, panels, content areas
Layer 2:            elevated    #1c1a24   — modals, dropdowns, hover popups
Layer 3:            overlay     rgba(0,0,0,0.60) — fullscreen overlays, dimming
```

Each layer gets progressively lighter, creating a natural sense of depth. No element should be lighter than `surface_hover` (`#252330`) except the accent color.

---

## 14. Iconography

### Style

- **Line icons**, 1.5px stroke weight, rounded caps and joins
- Size: 16px for inline, 20px for nav, 24px for empty states
- Color: `text_muted` by default, `text_secondary` on hover, `accent` on active/focus
- Source: Use simple QPainter-drawn icons or bundled SVGs — no icon font dependency

### Required Icons

| Icon | Used In | Description |
|---|---|---|
| Search (magnifier) | Search bar | Circle + diagonal line |
| Home | Nav bar | Simple house outline |
| Grid | Library nav | 2x2 square grid |
| Settings (gear) | Nav bar | Gear/cog outline |
| Folder | File manager nav | Folder outline |
| Back arrow | Detail page | Left-pointing chevron |
| Close (X) | Window control | X shape |
| Minimize (—) | Window control | Horizontal line |
| Maximize (□) | Window control | Square outline |
| Sort (A-Z) | Sort pills | A↓Z stacked |
| Clock | Recent sort | Clock outline |
| Play (▶) | Launch button | Right triangle |
| Controller | Empty state | Gamepad silhouette |
| Check (✓) | Toggles, confirmations | Checkmark |

---

## 15. Responsive Behavior

### Window Size Handling

| Width | Tiles per row | Side margins | Tile size |
|---|---|---|---|
| 1280px (min) | 5 | 32px | 220x308 |
| 1440px | 5-6 | 32px | 220x308 |
| 1920px | 7-8 | 48px | 220x308 |
| 2560px+ | 10+ | 48px | 220x308 |

Tile size is FIXED at 220x308. The grid adjusts the number of columns based on available width. This ensures consistent visual density.

### Minimum Window Size

- Width: 1024px (absolute minimum, 4 tiles + margins)
- Height: 640px
- Default: 1280x720

---

## 16. Implementation Mapping

### What Changes from Current Codebase

| Current | New | Reason |
|---|---|---|
| background `#08080c` | `#0b0a10` | Warmer undertone |
| primary `#0f0f15` | `#13121a` (surface) | Warmer, renamed for clarity |
| secondary `#161620` | `#1c1a24` (surface_elevated) | Warmer, renamed |
| text_color `#e8e8f0` | `#f0eef5` (text_primary) | Slightly warmer white |
| text_secondary `#6b6b80` | `#8a8698` | Much brighter — old was too dim |
| accent `#e94560` | `#e94560` (unchanged) | Already excellent |
| Tile 300x420 | 220x308 | Better density, more games visible |
| Sidebar 60px | 52px | Less chrome, more content |
| Grid gap 24px | 20px | Tighter, more efficient |
| Corner radius 14px (tiles) | 10px | More refined, less bubbly |

### ThemeManager Template Variables to Add

```python
# New tokens needed in _template_variables():
"surface": self._surface,           # renamed from primary
"surface_elevated": ...,            # renamed from secondary
"surface_hover": lighter(surface, 14),
"accent_hover": lighter(accent, 25),
"accent_pressed": darker(accent, 20),
"accent_atmospheric": f"rgba({ar}, {ag}, {ab}, 0.05)",
"text_primary": self._text_color,   # alias
"text_muted": "#5c586a",
"border_hover": "rgba(255, 255, 255, 0.12)",
"shadow_color": "rgba(0, 0, 0, 0.40)",
```

---

## Summary: The Pixiis Visual Identity

Pixiis looks like a **matte-black display case in a warm room**. The surfaces are dark but never cold — touched with the faintest plum warmth. The coral accent is used sparingly but decisively: focus rings, the logo, active states, the launch button. It never screams; it glows.

Game art is the centerpiece. The UI exists to frame it, not compete with it. When you scroll through your library, it should feel like flipping through a curated collection — each tile a miniature movie poster, each row a shelf in your personal cinema.

Controller navigation is first-class. The focus ring is unmistakable — a warm coral glow that says "you are here" without being garish. Every transition is smooth but purposeful: 180ms for most interactions, no gratuitous animations, no bouncing, no sliding that delays you.

The overall impression: **quiet confidence**. This launcher knows what it is and doesn't try too hard.
