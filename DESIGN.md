---
name: A2Flow
themes: [light, dark]
colors:
  light:
    surface: '#f4f7ff'
    surface-dim: '#d8e2f4'
    glass: 'rgba(255, 255, 255, 0.55)'
    glass-strong: 'rgba(255, 255, 255, 0.72)'
    glass-border: 'rgba(255, 255, 255, 0.65)'
    glass-highlight: 'rgba(255, 255, 255, 0.85)'
    on-surface: '#0b1c30'
    on-surface-variant: '#475569'
    outline: 'rgba(15, 23, 42, 0.18)'
    outline-variant: 'rgba(15, 23, 42, 0.10)'
    primary: '#0e7c7b'
    on-primary: '#ffffff'
    primary-container: '#14b8a6'
    on-primary-container: '#ffffff'
    secondary: '#6366f1'
    on-secondary: '#ffffff'
    accent: '#0e7c7b'
    accent-soft: 'rgba(20, 184, 166, 0.18)'
    error: '#dc2626'
    on-error-container: '#7f1d1d'
    success: '#10b981'
    bg-blob-1: 'rgba(94, 234, 212, 0.50)'
    bg-blob-2: 'rgba(165, 180, 252, 0.55)'
    bg-blob-3: 'rgba(252, 211, 170, 0.48)'
    bg-blob-4: 'rgba(186, 230, 253, 0.45)'
  dark:
    surface: '#050912'
    surface-dim: '#0a1224'
    glass: 'rgba(15, 23, 42, 0.45)'
    glass-strong: 'rgba(15, 23, 42, 0.65)'
    glass-border: 'rgba(148, 163, 184, 0.20)'
    glass-highlight: 'rgba(148, 163, 184, 0.35)'
    on-surface: '#e2e8f0'
    on-surface-variant: '#94a3b8'
    outline: 'rgba(148, 163, 184, 0.28)'
    outline-variant: 'rgba(148, 163, 184, 0.14)'
    primary: '#5eead4'
    on-primary: '#022c22'
    primary-container: 'rgba(94, 234, 212, 0.18)'
    on-primary-container: '#99f6e4'
    secondary: '#a78bfa'
    on-secondary: '#1e1b4b'
    accent: '#5eead4'
    accent-soft: 'rgba(94, 234, 212, 0.18)'
    error: '#fb7185'
    on-error-container: '#fecdd3'
    success: '#34d399'
    bg-blob-1: 'rgba(45, 212, 191, 0.32)'
    bg-blob-2: 'rgba(167, 139, 250, 0.32)'
    bg-blob-3: 'rgba(244, 114, 182, 0.26)'
    bg-blob-4: 'rgba(56, 189, 248, 0.24)'
typography:
  h1:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  h2:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  h3:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.04em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  mono-log:
    fontFamily: monospace
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.08em
  badge:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 12px
rounded:
  sm: 0.375rem
  DEFAULT: 0.5rem
  md: 0.5rem
  lg: 0.75rem
  xl: 1rem
  2xl: 1.25rem
  full: 9999px
spacing:
  container-padding: 2rem
  sidebar-width: 256px
  gutter: 1.5rem
  card-padding: 1.5rem
  stack-sm: 0.5rem
  stack-md: 1rem
glass:
  blur: 20px
  blur-strong: 24px
  saturate: 150%
  border: 1px solid var(--color-glass-border)
  inner-highlight: 'inset 0 1px 0 rgba(255, 255, 255, 0.6)'
  shadow-sm: '0 10px 32px rgba(15, 23, 42, 0.08)'
  shadow-lg: '0 28px 60px -16px rgba(15, 23, 42, 0.18)'
  shadow-glow: '0 0 36px rgba(20, 184, 166, 0.32)'
motion:
  duration-fast: 150ms
  duration-base: 240ms
  duration-slow: 360ms
  ease-standard: 'cubic-bezier(0.2, 0, 0, 1)'
  ease-emphasized: 'cubic-bezier(0.3, 0, 0, 1)'
  ease-exit: 'cubic-bezier(0.3, 0, 0.8, 0.15)'
  spring-gentle: '{ tension: 220, friction: 28 }'
  spring-snappy: '{ tension: 320, friction: 26 }'
  spring-bouncy: '{ tension: 260, friction: 18 }'
---

## Brand & Style

A2Flow's interface is engineered for AI-driven workflow automation. The visual language pairs **frosted-glass surfaces** with a vibrant, gently-animated mesh-gradient canvas — evoking **Depth, Clarity, and Forward Motion**.

The personality is futuristic-yet-trustworthy: glassmorphism gives the UI a sense of layered transparency without sacrificing legibility. Bright accent gradients (teal → indigo) signal interactivity and AI presence, while neutral text and high-contrast type keep the experience grounded for power users.

The system supports **light** and **dark** themes via a `data-theme` attribute on `<html>`, with all tokens cascading via CSS variables. The user's preference is persisted in `localStorage` (`a2flow.theme`) and falls back to `prefers-color-scheme`.

## Colors

The palette has two roles: a saturated **accent** (teal in light, neon mint in dark) for actions and highlights, and a **glass** family (translucent whites in light, translucent slates in dark) for surfaces.

- **Accent (`--color-accent`)** — Used for primary buttons, links, focus rings, active states, and the streaming caret. Pairs with the secondary indigo/violet for gradient fills (`from-accent to-secondary`).
- **Glass surfaces** — Three tiers (`glass`, `glass-strong`, plus `glass-highlight` for inner edges). Always rendered with `backdrop-filter: blur(20px) saturate(150%)`.
- **Background blobs** — Four soft radial gradients painted on `body::before` provide the colored "light" that the glass refracts. Blob colors differ between light and dark to match each theme's mood.
- **Semantic** — `error`, `success`, `alert` retained for status indication. `error-container` is rendered as translucent red.

## Typography

**Inter** continues to be the sole typeface. Heading sizes are unchanged from earlier MD3 baselines, but **letter-spacing tightens** (`tracking-tight`) for headings to lean into the futuristic feel. Label-caps now use `0.08em` tracking and 11px size for a sharper, more compressed look.

## Layout & Spacing

The app keeps the **Fixed Sidebar + Fluid Content** model. Sidebars are 256px wide and rendered as glass panels. Main content panels are centered with a max-width (`max-w-3xl` for chat, `max-w-6xl` for admin lists, `max-w-2xl` for forms) so glass panels feel like floating cards over the gradient canvas.

The 8px base spacing unit is preserved. Padding inside glass cards is 24px (`p-6`).

## Elevation & Depth

Depth is achieved through **layered translucency** rather than hard borders or heavy shadows.

- **Layer 0 (Canvas)** — `body::before` paints a fixed mesh of four radial gradients, slowly drifting via `float-slow` keyframes. `body::after` overlays a subtle SVG film-grain to break up banding.
- **Layer 1 (Glass)** — `.glass-panel`: 55–65% translucent fill, 20px blur + 150% saturate, 1px white-tinted border, soft drop shadow + inner-top highlight.
- **Layer 2 (Glass-Strong)** — `.glass-panel-strong`: 72% translucent fill, 24px blur, larger drop shadow. Used for floating chat input and admin form cards.
- **Glow** — Active/hover states emit a 36px accent glow (`shadow-glow`).

## Shapes

The shape language is **Soft Modern**.

- **Glass panels & cards:** `1.25rem` (20px) radius (`rounded-2xl`).
- **Buttons & inputs:** `1rem` (16px) radius (`rounded-xl`).
- **Chips & status badges:** `rounded-full` for pill shapes.
- **Active sidebar item indicator:** A 3px accent vertical bar on the left edge, with a soft glow.

## Components

- **Buttons:**
  - *Primary:* Gradient fill `from-accent to-secondary`, white text, inner-top highlight + soft accent shadow. Lifts 2px on hover with an accent glow.
  - *Secondary:* `glass-panel` background, on-surface text, accent text + glow on hover; lifts 2px (motion-safe).
  - *Ghost:* Transparent, on-surface-variant text, mild glass tint on hover; lifts 2px (motion-safe).
- **Inputs / Textareas / Selects:** `glass-panel` background with accent ring on focus (`ring-accent/50`). 16px radius.
- **Data Tables:** Wrapped in a 20px-radius `glass-panel`. Header uses a slightly stronger glass tint. Rows hover with an `accent-soft` wash.
- **Status Badges:** Pill-shaped, gradient or glass per state.
- **Chat bubbles:**
  - *User:* Accent gradient fill, asymmetric corner (`rounded-tr-md`), inner-top highlight.
  - *Assistant:* `glass-panel`, asymmetric corner (`rounded-tl-md`), accent-colored streaming caret.
- **A2UI surfaces:** `customCard` is rendered as `glass-panel-strong`. `customChoicePicker` chips use the same primary-gradient when selected and `glass-panel` when not, and scale up slightly (~1.03) on hover (motion-safe).
- **Theme Toggle:** A 36×36 round glass button in the chat header / admin sidebar bottom. Sun/Moon SVG icons; scales up slightly (~1.05) and emits accent glow on hover. Icons cross-fade with a 90° rotation on toggle.

## Motion

Motion follows a **Material You — "emphasized, gentle"** model: short durations, an emphasized easing curve for entrances, and React Spring physics for anything that mounts or unmounts. The intent is responsive without being chatty — every user action gets a small acknowledgement, never a long ceremony.

### Tokens (exposed as Tailwind v4 vars on `:root`)

| Token | Value | Use |
|-------|-------|-----|
| `--motion-duration-fast` | 150ms | Micro-interactions (icon hover, ✕ reveal) |
| `--motion-duration-base` | 240ms | Default for state transitions, button hovers |
| `--motion-duration-slow` | 360ms | Larger surface changes (modals, banners) |
| `--motion-ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | Default ease-out for transitions |
| `--motion-ease-emphasized` | `cubic-bezier(0.3, 0, 0, 1)` | Entrance choreography (message bubbles, lists) |
| `--motion-ease-exit` | `cubic-bezier(0.3, 0, 0.8, 0.15)` | Exit / dismiss animations |

### Spring presets (`@/lib/motion.ts`)

| Preset | Config | Use |
|--------|--------|-----|
| `gentle` | `{ tension: 220, friction: 28 }` | Default for entrance/exit, dialogs, list items |
| `snappy` | `{ tension: 320, friction: 26 }` | Brief feedback — theme toggle, send-button glow |
| `bouncy` | `{ tension: 260, friction: 18 }` | Reserved for playful confirmations |

Choose presets by intent (`useMotionConfig("gentle")`) rather than tuning tension/friction at call sites.

### Patterns

- **Entrance** — Message bubbles, error banners use the `animate-message-in` keyframe (`opacity 0→1` + `translateY(8px)→0` + slight `scale(0.985)→1`).
- **List staggering** — Session list rows use React Spring `useTransition` with `trail: 40` to ripple in horizontally on first load.
- **Modal** — `ConfirmDialog` cross-fades the backdrop and `scale(0.94)→1` the body with a gentle spring.
- **Buttons** — All variants share `active:scale-[0.97]` for tactile press feedback and lift 2px on hover (`motion-safe`-guarded).
- **Streaming caret** — Assistant bubble caret uses both `animate-blink` (the original step-start blink, preserved for tests) and `motion-safe:animate-pulse-cursor` (a softer opacity + scaleY pulse) so motion-safe users get the richer effect.
- **Theme toggle** — Scales up slightly on hover (motion-safe); Sun/Moon icons cross-fade with a 90° rotation via `useTransition`.

### Reduced motion

`@media (prefers-reduced-motion: reduce)` collapses every animation/transition to ~0ms in `globals.css`. React Spring code paths also call `useMotionConfig`, which detects the same preference and returns `{ duration: 0 }` so lifecycle callbacks still fire. Never assume animations will run — code defensively around their completion.
