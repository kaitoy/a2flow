---
name: A2Flow
themes: [light, dark]
colors:
  light:
    surface: 'oklch(0.975 0.008 240)'
    surface-dim: 'oklch(0.9 0.02 250)'
    glass: 'rgba(255, 255, 255, 0.55)'
    glass-strong: 'rgba(255, 255, 255, 0.72)'
    glass-overlay: 'rgba(255, 255, 255, 0.45)'
    glass-border: 'rgba(255, 255, 255, 0.65)'
    glass-highlight: 'rgba(255, 255, 255, 0.85)'
    on-surface: '#0b1c30'
    on-surface-variant: '#475569'
    outline: 'rgba(15, 23, 42, 0.18)'
    outline-variant: 'rgba(15, 23, 42, 0.10)'
    primary: 'oklch(0.56 0.12 183)'
    on-primary: '#ffffff'
    primary-container: 'oklch(0.72 0.14 178)'
    on-primary-container: '#ffffff'
    secondary: 'oklch(0.58 0.17 292)'
    on-secondary: '#ffffff'
    accent: 'oklch(0.56 0.12 183)'
    accent-soft: 'oklch(0.72 0.14 178 / 0.18)'
    error: '#dc2626'
    on-error-container: '#7f1d1d'
    success: '#10b981'
    bg-aurora-1: 'oklch(0.85 0.13 178 / 0.55)'
    bg-aurora-2: 'oklch(0.75 0.15 292 / 0.40)'
    bg-aurora-3: 'oklch(0.88 0.06 210 / 0.50)'
  dark:
    surface: 'oklch(0.13 0.025 262)'
    surface-dim: 'oklch(0.18 0.03 262)'
    glass: 'rgba(15, 23, 42, 0.45)'
    glass-strong: 'rgba(15, 23, 42, 0.65)'
    glass-overlay: 'rgba(15, 23, 42, 0.38)'
    glass-border: 'rgba(148, 163, 184, 0.20)'
    glass-highlight: 'rgba(148, 163, 184, 0.35)'
    on-surface: '#e2e8f0'
    on-surface-variant: '#94a3b8'
    outline: 'rgba(148, 163, 184, 0.28)'
    outline-variant: 'rgba(148, 163, 184, 0.14)'
    primary: 'oklch(0.87 0.16 170)'
    on-primary: 'oklch(0.24 0.05 175)'
    primary-container: 'oklch(0.87 0.16 170 / 0.16)'
    on-primary-container: 'oklch(0.93 0.10 170)'
    secondary: 'oklch(0.72 0.16 295)'
    on-secondary: 'oklch(0.30 0.12 295)'
    accent: 'oklch(0.87 0.16 170)'
    accent-soft: 'oklch(0.87 0.16 170 / 0.16)'
    error: '#fb7185'
    on-error-container: '#fecdd3'
    success: '#34d399'
    bg-aurora-1: 'oklch(0.80 0.15 172 / 0.30)'
    bg-aurora-2: 'oklch(0.60 0.19 295 / 0.32)'
    bg-aurora-3: 'oklch(0.75 0.10 220 / 0.16)'
typography:
  h1:
    fontFamily: Space Grotesk
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.02em
  h2:
    fontFamily: Space Grotesk
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
    fontFamily: JetBrains Mono
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
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 12px
rounded:
  xs: 0.125rem
  sm: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  2xl: 1rem
  3xl: 1.5rem
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
  shadow-glow: '0 0 36px oklch(0.72 0.14 178 / 0.35)'
motion:
  duration-fast: 150ms
  duration-base: 240ms
  duration-slow: 360ms
  ease-standard: 'cubic-bezier(0.2, 0, 0, 1)'
  ease-emphasized: 'cubic-bezier(0.3, 0, 0, 1)'
  ease-exit: 'cubic-bezier(0.3, 0, 0.8, 0.15)'
  live-sweep: '2.4s linear infinite'
  spring-gentle: '{ tension: 220, friction: 28 }'
  spring-snappy: '{ tension: 320, friction: 26 }'
  spring-bouncy: '{ tension: 260, friction: 18 }'
---

## Brand & Style

A2Flow's interface is engineered for AI-driven workflow automation. The visual language pairs **frosted-glass surfaces** with a single **aurora ribbon** — one band of light flowing diagonally across the canvas — evoking **Depth, Clarity, and Forward Motion**.

The personality is futuristic-yet-trustworthy: glassmorphism gives the UI a sense of layered transparency without sacrificing legibility, and the palette is deliberately concentrated. One accent (aurora mint) carries every interactive signal; the violet in the aurora's body exists only as light for the glass to refract, never as a competing UI accent. All brand hues are defined in `oklch()` rather than framework presets. Space Grotesk headings and JetBrains Mono data text keep the experience grounded for power users, and the signature **live edge** — accent light circling a panel's border while an agent works — makes "the system is flowing" visible.

The system supports **light** and **dark** themes via a `data-theme` attribute on `<html>`, with all tokens cascading via CSS variables. The user's preference is persisted in `localStorage` (`a2flow.theme`) and falls back to `prefers-color-scheme`.

## Colors

The palette is a **single-accent system** defined in `oklch()`: one saturated **accent** (deep aquamarine in light, luminous aurora mint in dark) for every action and highlight, a supporting **aurora violet** confined to gradients and the background canvas, and a **glass** family (translucent whites in light, translucent slates in dark) for surfaces. Concentrating the visible hues into one mint-to-violet family is what gives the UI its impact — status colors aside, nothing else on screen competes with the accent.

- **Accent (`--color-accent`)** — Used for primary buttons, links, focus rings, active states, the streaming caret, and the live edge. Pairs with the secondary aurora violet for gradient fills (`from-accent to-secondary`); the violet never appears alone as a UI accent.
- **Glass surfaces** — Tiers: `glass`, `glass-strong`, `glass-overlay` (more translucent fill for floating popovers), plus `glass-highlight` for inner edges. Always rendered with a `backdrop-filter` blur + saturate (applied via Tailwind's `backdrop-blur`/`backdrop-saturate` utilities — see [Elevation & Depth](#elevation--depth)).
- **Aurora ribbon** — A single diagonal band of light painted on `body::before` (`bg-aurora-1` mint head, `bg-aurora-2` violet body, `bg-aurora-3` soft-cyan tail) provides the colored "light" that the glass refracts. Aurora colors differ between light and dark to match each theme's mood.
- **Semantic** — `error`, `success`, `alert` retained for status indication. `error-container` is rendered as translucent red.

## Typography

Three typefaces, three jobs — the pairing itself is part of the identity:

- **Space Grotesk** (`--font-display`, the `font-display` utility) is the display face for **all h1/h2 headings** and the "A2Flow" wordmark, giving titles a geometric, technical character. h1 grows to 30px so the scale contrast between a page title and its body is unmistakable.
- **Inter** remains the body face for text, labels, and small headings (h3 and below).
- **JetBrains Mono** (`--font-jetbrains-mono`, resolved by Tailwind's `font-mono` utility) is the data face — logs (`mono-log`), timestamps, session/tool IDs, and tag chips. Agent activity is A2Flow's raw material, and rendering it in a designed monospace instead of the generic system stack makes that material part of the brand.

Headings keep **tight letter-spacing** (`tracking-tight`) to lean into the futuristic feel. Label-caps use `0.08em` tracking and 11px size for a sharper, more compressed look. The `badge` scale (11px / 700 / 12px line-height, JetBrains Mono) is implemented as the `text-badge` utility — used for small numeric/tag chips (`NotificationBell`'s unread count, `ToolActivityBubble`'s "MCP" tag). Badges are counts and tags — machine data — so they render in the mono data face, but keep their own scale without label-caps' forced uppercase/tracking/color, since badge color and case vary by call site.

## Layout & Spacing

The app keeps the **Fixed Sidebar + Fluid Content** model. Sidebars are 256px wide and rendered as glass panels. Main content panels are centered with a max-width (`max-w-3xl` for chat, `max-w-6xl` for admin lists, `max-w-2xl` for forms) so glass panels feel like floating cards over the gradient canvas.

The 8px base spacing unit is preserved. Padding inside glass cards is 24px (`p-6`).

## Elevation & Depth

Depth is achieved through **layered translucency** rather than hard borders or heavy shadows.

- **Layer 0 (Canvas)** — `body::before` paints the fixed **aurora ribbon**: a single band of radial gradients flowing diagonally from the upper-left (mint head) through the center (violet body) to the lower-right (soft-cyan tail), with a faint counter-glow in the opposite corner for balance. It drifts very slowly along its own flow direction via the `aurora-drift` keyframes — ambient weather, not an animation. `body::after` overlays a subtle SVG film-grain to break up banding.
- **Layer 1 (Glass)** — `.glass-panel`: 55–65% translucent fill, 20px blur + 150% saturate, 1px white-tinted border, soft drop shadow + inner-top highlight.
- **Layer 2 (Glass-Strong)** — `.glass-panel-strong`: 72% translucent fill, 24px blur, larger drop shadow. Used for floating chat input and admin form cards.
- **Layer 2b (Glass-Overlay)** — `.glass-panel-overlay`: large shadow like glass-strong but a more translucent fill (light 45%, dark 38%) and a lighter 16px blur, so content reads through floating popovers more clearly. Used for tooltips, dropdown/list menus (user menu, notification panel), and modal dialogs (`ConfirmDialog`, `RegistrySearchDialog`).
- **Chrome (Glass-Chrome)** — `.glass-chrome`: the edge-to-edge frame surfaces (app header, sidebars, timeline rail): the `glass` fill with a 24px blur + 150% saturate but no border or shadow of its own — each call site draws only the single edge border (`border-b`/`border-r border-glass-border`) its layout needs.
- **Glow** — Active/hover states emit a 36px accent glow (`shadow-glow`).

> **Note** — The `backdrop-filter` blur on all glass tiers is applied through Tailwind's `backdrop-blur-*`/`backdrop-saturate-*` utilities via `@apply`, not a raw `backdrop-filter` declaration: Tailwind v4 composes `backdrop-filter` from `--tw-backdrop-*` custom properties and silently drops a bare declaration written inside an `@utility`.

## Shapes

The shape language is **Soft Modern**.

- **Glass panels & cards:** `1rem` (16px) radius (`rounded-2xl`).
- **Buttons & inputs:** `0.75rem` (12px) radius (`rounded-xl`).
- **Chips & status badges:** `rounded-full` for pill shapes.
- **Active sidebar item indicator:** A 3px accent vertical bar on the left edge, with a soft glow.

## Accessibility

- **Focus ring** — Every interactive element (buttons, inputs, textareas, selects, custom clickable elements) uses `focus-visible:ring-2 focus-visible:ring-accent/50` as its keyboard-focus treatment. This is already consistent across ~15 components (`components/ui/button.tsx`, `ThemeToggle.tsx`, `NotificationBell.tsx`, `UserMenu.tsx`, etc.) — reuse it rather than inventing a one-off focus style for a new component.
- **ARIA attributes** — Interactive or dynamically-updating elements carry appropriate `aria-label`, `aria-live`, and `role` (e.g. `role="menu"` for dropdowns) attributes. Purely decorative icons stay `aria-hidden` (see Iconography); an icon that carries standalone meaning gets a label instead.

## Components

- **Buttons:**
  - *Primary:* Gradient fill `from-accent to-secondary`, white text, inner-top highlight + soft accent shadow. Lifts 2px on hover with an accent glow.
  - *Secondary:* `glass-panel` background, on-surface text, accent text + glow on hover; lifts 2px (motion-safe).
  - *Ghost:* Transparent, on-surface-variant text, mild glass tint on hover; lifts 2px (motion-safe).
  - *Submitting state:* Buttons that send a server request (Save, Sign in, Approve/Reject, Load more) pass a `status` to the shared `Button` and cycle their label through three stages — idle → `pendingLabel` → `doneLabel` (e.g. `Save → Saving… → Saved!`), reverting to idle ~2s after success. All three labels are stacked in one grid cell so the button **reserves the widest label's width and never reflows** — the same "reserve layout to avoid a swap-time jump" intent as the **Skeleton**. The hidden sizer copies are `aria-hidden` so the button keeps its visible label as its accessible name. State is driven by the `useAsyncAction` hook (see Motion → Patterns).
  - *Success (`done`) state:* While "Saved!" shows, the button turns **solid success-green** (`--color-success`, overriding the variant's fill/gradient) with a leading **checkmark** icon and a matching green glow, and plays a one-shot celebratory **wiggle** (`motion-safe`). It is held **non-interactive** (rendered `disabled`, but kept at full opacity) for the whole ~2s so a completed save cannot be re-triggered. `pending` is likewise non-interactive but keeps the standard dimmed `disabled` look. Reduced-motion keeps the green + checkmark but drops the shake.
- **Inputs / Textareas / Selects:** `glass-panel` background with accent ring on focus (`ring-accent/50`). 12px radius. Placeholder text uses `placeholder:text-on-surface-variant/50` — not the bare `on-surface-variant` token — so it stays visibly lighter than filled-in values (`text-on-surface`) instead of reading as near-identical secondary text.
- **Data Tables:** Wrapped in a 16px-radius `glass-panel`, `border-collapse`. Header uses a stronger glass tint (`glass-strong/70`) with a `divider` underline so it reads clearly apart from the body. Columns and rows are separated by `divider` grid lines — a dedicated token tinted dark in light mode and light in dark mode so it stays visible where the near-white `glass-border` would vanish (full strength in the header, `/60` in the body). Body rows are zebra-striped via the `even:` variant (`glass-strong/15`); hover overrides with an `accent-soft` wash. Each header cell carries a draggable resize strip on its right edge that tints `accent` on hover. Sort is a header pill (chevron tinted `accent` when active) and filter is a square `h-6 w-6` icon button with an `accent` dot when a filter is applied. By default every text cell clips to one line with an overflow tooltip; columns rendering interactive or multi-line content opt out. While loading, the body shows shimmering **skeleton** rows that mirror the column layout (no spinner) so the table never reflows on data arrival.
- **Skeleton:** Shimmering placeholder surface (`@utility skeleton`: a tinted `--skeleton-base` block with a brighter `--skeleton-sheen` band swept across by `--animate-shimmer`). Both tokens are theme-tuned so the shimmer reads clearly against light and dark glass panels. Used to reserve layout during data fetches — list rows, edit-form fields, and the workflow chat view — so content swaps in without jump or blank flash. Reduced-motion collapses it to a static block.
- **Status Badges:** Pill-shaped, gradient or glass per state.
- **Chat bubbles:**
  - *User:* Accent gradient fill, asymmetric corner (`rounded-tr-md`), inner-top highlight.
  - *Assistant:* `glass-panel`, asymmetric corner (`rounded-tl-md`), accent-colored streaming caret. Content is rendered as **Markdown** (see Markdown content below). While streaming, the bubble carries the signature **live edge** (see Motion → Patterns).
  - *Reasoning ("thinking"):* `ReasoningBubble` — a dashed-border, italic panel (`bg-glass`, asymmetric `rounded-tl-md` corner like the assistant bubble) labelled with a 💭 "Thinking" header, rendering the agent's streamed reasoning text below the reply's normal weight and color. Renders nothing until reasoning text arrives. While the agent is still reasoning and hasn't started a reply yet, it carries the signature **live edge** in place of the generic "Agent is thinking…" pulse.
- **Markdown content:** Agent-generated Markdown (assistant chat bubbles and the A2UI `Text` component) is rendered to HTML by `marked` and styled by the `markdown-body` utility (globals.css) — the single source of truth restoring what Tailwind preflight strips: heading scale (display face for h1/h2, tight tracking), list bullets, mono `code`/`pre` blocks on a `surface-container-high` tint with `overflow-x` scrolling, accent-colored links, `divider` rules, and outline-bordered tables, all sized to the 14px body scale.
- **A2UI surfaces:** `customCard` is rendered as `glass-panel-strong`. `customChoicePicker` chips use the same primary-gradient when selected and `glass-panel` when not, and scale up slightly (~1.03) on hover (motion-safe).
- **Theme Toggle:** A 36×36 round glass button in the chat header / admin sidebar bottom. Sun/Moon SVG icons; scales up slightly (~1.05) and emits accent glow on hover. Icons cross-fade with a 90° rotation on toggle.
- **EmptyState:** Centered placeholder for empty regions (no messages, no rows, no sessions). Pairs an `AnimatedIcon` inside a frosted-glass tile with an optional title and description. Has a `compact` variant for tight containers (session sidebar, table empty cell). See `@/components/ui/empty-state.tsx`.
- **Route loading/error boundaries:** Every route segment has a `loading.tsx` built from the same shared skeleton the page's own post-mount loading state uses (`FormSkeleton`, `AdminListSkeleton`, `WorkflowSessionSkeleton`, `ChatPanelSkeleton`) so the Suspense fallback and the page's own loading state are visually identical. Shells with persistent chrome (root, `/admin`, `(chat)`, `/account`) each have an `error.tsx` built on `RouteErrorFallback` (`EmptyState` + `Button reset`) so a render crash doesn't unmount the section's sidebar/header; `global-error.tsx` is the last-resort fallback for a crash in the root layout itself. A single root `not-found.tsx` handles unmatched URLs.

### Iconography

Icons come from [`lucide-react`](https://lucide.dev) (stroke icons, `strokeWidth={1.8}` to match the app's hand-drawn glyphs, `currentColor` for theme tinting). Wrap any icon that should animate in `AnimatedIcon` (`@/components/ui/animated-icon.tsx`), which applies a `motion-safe`-gated looping animation (`bob`, `breathe`, `spin-slow`, `spin-occasional`, `wiggle`, or `none`). Decorative icons are `aria-hidden` by default — add a label when an icon carries standalone meaning. Admin list headers pass an `icon` to `AdminPageHeader` (and the matching `emptyIcon` to `DataTable`) so each section reads at a glance; both twirl occasionally (`spin-occasional`) rather than bobbing.

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
- **Modal** — `ConfirmDialog` cross-fades the backdrop and `scale(0.94)→1` the body with a gentle spring. The scrim carries only a light `backdrop-blur-sm` (4px) — most of the frosted look comes from the panel's own `glass-panel-overlay` blur, so the scrim stays light enough that colorful content is still visible for the panel to refract.
- **Buttons** — All variants share `active:scale-[0.97]` for tactile press feedback and lift 2px on hover (`motion-safe`-guarded). Server-submitting buttons additionally use **optimistic UI** via `useAsyncAction`: the button disables immediately on click (preventing double-submits), and the `pending` label ("Saving…") only appears if the response takes longer than 200ms — fast responses skip straight to the `done` label, so quick saves never flash a transient "Saving…". On success the button stays non-interactive and celebrates with a green fill, checkmark, and one-shot `wiggle` (see Components → Buttons → Success state). The label width is fixed (see Components → Buttons) so none of these transitions reflow the button.
- **Live edge (signature)** — While an agent is streaming (assistant bubble), a tool is running (`ToolActivityBubble`'s pill), the agent is still reasoning with no reply text yet (`ReasoningBubble`'s panel), or the agent is working with nothing else on screen yet (`WorkingIndicator`'s "Agent is thinking…" pill), the `live-edge` utility sends a comet of accent light around the panel's border: a conic gradient whose `from` angle (`@property --live-angle`) rotates via the `live-sweep` keyframes (2.4s linear), masked down to a thin ring on an overlay pseudo-element. These four surfaces are the only carriers — this is the one place the UI spends continuous motion, and it means "the flow is live", so never apply it decoratively to idle surfaces (in-progress workflow entries keep their calmer accent tint/glow instead). Reduced-motion swaps the sweep for a static translucent accent ring.
- **Streaming caret** — Assistant bubble caret uses both `animate-blink` (the original step-start blink, preserved for tests) and `motion-safe:animate-pulse-cursor` (a softer opacity + scaleY pulse) so motion-safe users get the richer effect.
- **Theme toggle** — Scales up slightly on hover (motion-safe); Sun/Moon icons cross-fade with a 90° rotation via `useTransition`.
- **Decorative icons** — Accent icons in empty states and page headers loop through small-amplitude keyframes, all `motion-safe`-gated: `bob` (gentle ±4px float, chat/sidebar empty states), `breathe` (subtle scale + opacity swell, chat empty state), `spin-slow` (9s continuous rotation), `spin-occasional` (a quick full turn around the Y/vertical axis — a coin-like flip with `perspective` depth — every ~8s on a long rest, used by admin header and admin empty-table icons), `wiggle` (one-shot ±10° shake), and `attention` (a brief wiggle on a long rest, used by the notification bell when there are unread items). Kept deliberately distinct from the large-amplitude background drifts (`float-slow`/`float-slower`).

### Reduced motion

`@media (prefers-reduced-motion: reduce)` collapses every animation/transition to ~0ms in `globals.css`. React Spring code paths also call `useMotionConfig`, which detects the same preference and returns `{ duration: 0 }` so lifecycle callbacks still fire. Never assume animations will run — code defensively around their completion.
