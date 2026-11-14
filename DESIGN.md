---
name: A2Flow
themes: [light, dark]
colors:
  light:
    surface: 'oklch(0.972 0.005 215)'
    surface-dim: 'oklch(0.94 0.008 215)'
    panel: '#ffffff'
    panel-raised: '#ffffff'
    chrome: 'oklch(0.99 0.003 215 / 0.72)'
    glass: 'oklch(0.22 0.025 228 / 0.045)'
    glass-strong: 'oklch(0.22 0.025 228 / 0.09)'
    glass-overlay: 'rgba(255, 255, 255, 0.9)'
    glass-border: 'oklch(0.22 0.025 228 / 0.12)'
    glass-highlight: 'oklch(0.8 0.14 176)'
    on-surface: 'oklch(0.22 0.025 228)'
    on-surface-variant: 'oklch(0.47 0.02 228)'
    outline: 'oklch(0.22 0.025 228 / 0.24)'
    outline-variant: 'oklch(0.22 0.025 228 / 0.12)'
    primary: 'oklch(0.52 0.105 184)'
    on-primary: '#ffffff'
    primary-container: 'oklch(0.52 0.105 184 / 0.12)'
    on-primary-container: 'oklch(0.36 0.08 184)'
    secondary: 'oklch(0.58 0.17 292)'
    on-secondary: '#ffffff'
    accent: 'oklch(0.52 0.105 184)'
    accent-soft: 'oklch(0.52 0.105 184 / 0.1)'
    bubble: 'oklch(0.52 0.105 184)'
    on-bubble: '#ffffff'
    error: '#dc2626'
    on-error-container: '#7f1d1d'
    success: 'oklch(0.52 0.13 158)'
    bg-aurora-1: 'oklch(0.88 0.08 178 / 0.5)'
    bg-aurora-2: 'oklch(0.9 0.05 215 / 0.55)'
  dark:
    surface: 'oklch(0.165 0.02 225)'
    surface-dim: 'oklch(0.13 0.018 225)'
    panel: 'oklch(0.205 0.022 225)'
    panel-raised: 'oklch(0.235 0.024 225)'
    chrome: 'oklch(0.185 0.021 225 / 0.72)'
    glass: 'oklch(0.93 0.01 215 / 0.06)'
    glass-strong: 'oklch(0.93 0.01 215 / 0.1)'
    glass-overlay: 'oklch(0.215 0.022 225 / 0.88)'
    glass-border: 'oklch(0.93 0.01 215 / 0.1)'
    glass-highlight: 'oklch(0.97 0.06 172)'
    on-surface: 'oklch(0.93 0.01 215)'
    on-surface-variant: 'oklch(0.72 0.02 220)'
    outline: 'oklch(0.93 0.01 215 / 0.24)'
    outline-variant: 'oklch(0.93 0.01 215 / 0.12)'
    primary: 'oklch(0.86 0.15 172)'
    on-primary: 'oklch(0.22 0.04 185)'
    primary-container: 'oklch(0.86 0.15 172 / 0.16)'
    on-primary-container: 'oklch(0.93 0.1 172)'
    secondary: 'oklch(0.72 0.16 295)'
    on-secondary: 'oklch(0.30 0.12 295)'
    accent: 'oklch(0.86 0.15 172)'
    accent-soft: 'oklch(0.86 0.15 172 / 0.14)'
    bubble: 'oklch(0.4 0.075 184)'
    on-bubble: 'oklch(0.96 0.02 180)'
    error: '#fb7185'
    on-error-container: '#fecdd3'
    success: '#34d399'
    bg-aurora-1: 'oklch(0.62 0.12 178 / 0.2)'
    bg-aurora-2: 'oklch(0.55 0.09 225 / 0.22)'
typography:
  h1:
    fontFamily: Archivo
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.02em
    fontStretch: 112%
  h2:
    fontFamily: Archivo
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
    fontStretch: 112%
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
    fontFamily: Geist Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  badge:
    fontFamily: Geist Mono
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 12px
rounded:
  xs: 0.125rem
  sm: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.5rem
  2xl: 0.75rem
  3xl: 1.5rem
  full: 9999px
spacing:
  container-padding: 2rem
  sidebar-width: 256px
  gutter: 1.5rem
  card-padding: 1.5rem
  stack-sm: 0.5rem
  stack-md: 1rem
surfaces:
  border: 1px solid var(--color-glass-border)
  overlay-blur: 20px
  chrome-blur: 12px
  saturate: 140%
  shadow-panel: '0 1px 2px oklch(0.22 0.025 228 / 0.05)'
  shadow-raised: '0 1px 2px oklch(0.22 0.025 228 / 0.05), 0 10px 28px -14px oklch(0.22 0.025 228 / 0.16)'
  shadow-overlay: '0 2px 6px oklch(0.22 0.025 228 / 0.08), 0 20px 48px -16px oklch(0.22 0.025 228 / 0.3)'
  shadow-glow: '0 0 0 3px oklch(0.52 0.105 184 / 0.18)'
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

A2Flow's interface is a calm instrument for AI-driven workflow automation, built on one rule: **quiet until it flows**. At rest nothing moves and nothing glows — opaque panels on hairlines, ink-colored headings, one teal accent. Light is reserved for the moment an agent is working: the signature **live edge**, accent light circling a panel's border, is the only light on screen that travels, and it travels because a run is in flight.

Four principles follow from that rule:

1. **Light means the agent is working.** Glow and travelling light are spent on generative runs only. Hover, selection and success are stated with a border, a ring, a fill or a glyph.
2. **One accent, solid.** The logo's teal carries every interactive signal as a flat fill — never as half of a gradient. Violet is a categorical color only.
3. **Content is opaque; only what floats is glass.** Text sits on solid surfaces. Translucency is kept for the layers with something underneath them: the header and sidebars, popovers, dialogs.
4. **Headings speak through the typeface.** No gradient text. The display voice is Archivo's width.

All brand hues are defined in `oklch()` rather than framework presets. Archivo headings and Geist Mono data text keep the experience grounded for power users.

The system supports **light** and **dark** themes via a `data-theme` attribute on `<html>`, with all tokens cascading via CSS variables. The user's preference is persisted in `localStorage` (`a2flow.theme`) and falls back to `prefers-color-scheme`.

## Colors

The palette is a **single-accent system** defined in `oklch()`: one **accent** (deep teal in light, luminous mint in dark) for every action and highlight, neutrals that lean toward that same teal (hue 215–228) instead of a slate blue, and a small set of semantic and categorical colors. Nothing else on screen competes with the accent.

- **Accent (`--color-accent`)** — Used for primary buttons, links, focus rings, active states, the streaming caret, and the live edge. Always a solid fill. In light it is deep enough (`oklch(0.52 …)`) that white text on it clears 4.5:1; in dark it lifts to a luminous mint and carries dark text.
- **Bubble (`--color-bubble` / `--color-on-bubble`)** — The viewer's own chat bubble. The accent itself in light; in dark the accent is right for a button and far too loud for a paragraph-sized fill, so the bubble takes a deep teal with near-white text there.
- **Surfaces** — `surface` is the canvas and `surface-dim` its recessed wells. `panel` and `panel-raised` are the opaque fills of the two content tiers. Only `chrome` (header, sidebars) and `glass-overlay` (popovers, dialogs) are translucent — see [Elevation & Depth](#elevation--depth).
- **Washes and hairlines** — `glass` and `glass-strong` are thin washes of the ink color (hover fills, a highlighted row, the table header's tint); `glass-border` is the one hairline every panel and divider is drawn with; `glass-highlight` is the bright head of the live edge's comet. The `glass` in these names is historical — they predate the opaque panels.
- **Canvas light** — `body::before` paints two still washes along the top edge of the canvas: `bg-aurora-1` (mint, upper-left) and `bg-aurora-2` (a paler cyan, upper-right). They do not move.
- **Violet (`--color-secondary`)** — A categorical color only: another participant's chat bubble, one tag slot, the avatar palette. It never appears on a control and never as a gradient stop.
- **Semantic** — `error`, `success`, `alert` retained for status indication. `error-container` is rendered as translucent red.
- **Tag palette** — The one categorical palette in the system, for user-created [tags](https://kaitoy.github.io/a2flow/docs/guides/tags): eight slots (`mint`, `teal`, `cyan`, `indigo`, `violet`, `rose`, `amber`, `slate`) defined as `--c-tag-*` in `globals.css`, one value per slot per theme. They deliberately span more of the hue circle than the rest of the UI — the whole point of a tag color is to be told apart at a glance in a list — but each stays at roughly the accent's chroma and is rendered as a **tint**, never a fill: `.tag-chip` mixes 14% of the slot into the chip's background and 32% into its border, and takes the slot itself only for the text. A row of tags therefore reads as quiet metadata rather than competing with the single accent the UI is built around. The backend stores the *slot name*, never a color value, which is what lets light and dark carry different values (a chip needs contrast on both themes' panels) and lets the palette be retuned later without rewriting rows. `frontend/src/lib/tag-palette.ts` maps a slot to its class; `.tag-swatch` draws the same slot as a solid dot — used both as the marker beside a `CheckboxGroup` option and as the pressable target in the tag picker dialog's color filter, where an unpressed swatch simply drops to `opacity-45` rather than changing hue. A third class, `.tag-chip-selected`, is the pressed state of a toggle chip: the same slot at roughly double the tint with a near-full-strength border and an inset hairline, so the vocabulary grid can show what is chosen without borrowing the focus ring's outline.
- **Avatar palette** — Generated user avatars ([boring-avatars](https://github.com/boringdesigners/boring-avatars), `beam` variant) draw from a five-color palette defined in `frontend/src/lib/avatar-palette.ts`: `#16BFA9` (mint accent), `#0E8A7C` (deep teal), `#7F62D5` (violet), `#A7E8DC` (pale mint), `#CBD5E1` (slate neutral). It stays inside the mint-to-violet family so avatars read as part of the single-accent system rather than as a competing multi-hue palette. These are literal hex values, not `--c-*` custom properties, because the renderer takes the palette through a JS prop and parses each entry as hex; for the same reason one palette serves both themes instead of switching on `data-theme`. A user may override the palette from `/profile`.

## Typography

Three typefaces, three jobs — the pairing itself is part of the identity:

- **Archivo** (`--font-display`, the `font-display` utility) is the display face for **all h1/h2 headings** and the "A2Flow" wordmark. It is a variable font with a width axis, and the display voice *is* that width: `font-display` sets `font-stretch: 112%` (in the base layer, so a call site can widen it further), and the wordmark runs at 125%. Headings are set in the ink color — never as gradient text. h1 grows to 30px so the scale contrast between a page title and its body is unmistakable.
- **Inter** remains the body face for text, labels, and small headings (h3 and below).
- **Geist Mono** (`--font-geist-mono`, resolved by Tailwind's `font-mono` utility) is the data face — logs (`mono-log`), timestamps, session/tool IDs, and tag chips. Agent activity is A2Flow's raw material, and rendering it in a designed monospace instead of the generic system stack makes that material part of the brand. It is also the mono face of the manual's diagrams, so a tool name reads the same in the app and in the documentation.

Headings keep **tight letter-spacing** (`tracking-tight`). A field's or a section's small label uses the `text-label` utility — 12px / 500, sentence case, `on-surface-variant` — one step lighter than the value beneath it; column headers and menu section labels follow the same sentence-case treatment at `text-xs font-medium`. Nothing in the UI is set in tracked capitals except `Badge`, whose fixed vocabulary (`MCP`, `stdio`) is a marker rather than a label. The `badge` scale (11px / 700 / 12px line-height, Geist Mono) is implemented as the `text-badge` utility — used for small numeric and fixed-label badges (`NotificationBell`'s unread count, `ToolActivityBubble`'s "MCP" tag). Badges are counts and constant labels — machine data — so they render in the mono data face, with color and case left to the call site. The `Tags` column's tag chips are a separate case: they take `Chip`'s compact `xs` size — the same 11px mono, but at normal weight and natural case, so two of them stack within one table row (see Shapes).

### Japanese, Chinese and Korean

The three faces cover Latin script only, and no CJK web font is loaded: those run to several megabytes. Han, Kana and Hangul come from the system, and the `lang` attribute on `<html>` makes the browser pick the regional glyphs. System faces have no width axis, so `font-display`'s stretch simply does not apply to them. Under those languages all `tracking-*` utilities drop their letter-spacing, since these scripts read loosely when tracked.

## Layout & Spacing

The app keeps the **Fixed Sidebar + Fluid Content** model. Sidebars are 256px wide and rendered as `glass-chrome`. Main content panels are centered with a max-width (`max-w-3xl` for chat, `max-w-6xl` for admin lists, `max-w-2xl` for forms) so panels read as cards on the canvas. The one form that grows past `max-w-2xl` is an admin detail page's form once it has earned a second column — see below.

The 8px base spacing unit is preserved. Padding inside cards is 24px (`p-6`).

### Admin form pages

Admin create pages nest a `FormColumn` (`max-w-2xl`, centered) inside `AdminPageContainer`, so the form reads as a narrow floating card while the breadcrumb and title above it stay flush left at the page's full width.

Admin **detail** pages nest a `FormLayout` instead. It stacks exactly like `FormColumn` while cramped, then splits into a fluid main column plus a fixed **16rem** trailing column once it has `@4xl` (56rem) of room. The trailing column carries read-only record metadata (`AuditMeta`) that would otherwise push the form's actions off screen. Its 16rem matches the `sidebar-width` token, and the 24px gutter is the standard `gutter`.

The page header goes *inside* `FormLayout`'s main column rather than above it. Its right-hand action cluster then lines up with the form's right edge instead of the page's, so a page-level action (an agent skill's "Generate Workflow", say) reads as belonging to the form rather than to the metadata column.

A detail page names **the record, not the operation**: its `AdminPageHeader` title and the last crumb of its `Breadcrumbs` trail both carry the record's own name (a workflow's name, a user's username, a task template's title), never a verb like "Edit". The name is user-provided and unbounded, so the heading truncates rather than pushing the action cluster off the page, and the crumb truncates the same way. Until the record loads, the title renders a `Skeleton` bar and the crumb an ellipsis, so neither the heading's height nor the trail's shape shifts when the name lands.

### Responsive & touch

- **Container queries** — the admin shell reserves a 256px sidebar, so viewport width overstates how much room a page actually has. Anything that reflows because *the content area* got wider (`FormLayout`'s second column, `DetailList`'s second column) uses `@container` + an `@`-prefixed variant rather than a viewport breakpoint, and the component renders its own `@container` wrapper so it behaves correctly wherever it is dropped. Viewport breakpoints stay for shell-level and device-level decisions.
- **Breakpoint** — `md` (768px) is the shell breakpoint: below it every fixed sidebar hides (`max-md:hidden`) and is reachable instead through a hamburger button in the `AppHeader` that opens the same sidebar component inside the shared `SidebarDrawer` (an off-canvas panel over a dimmed scrim, dismissed by scrim tap or Escape, with the modal focus wiring from `useDialogA11y`). Never build a page-specific drawer — pass the sidebar into `SidebarDrawer`.
- **Viewport height** — full-screen shells use `h-dvh`/`min-h-dvh`, never `h-screen` (100vh), so mobile URL bars don't clip the bottom of the layout. The chat input pads its bottom with `env(safe-area-inset-bottom)`.
- **Touch (`pointer-coarse:`)** — hover-revealed controls must also be reachable on touch: make them always visible under `pointer-coarse:` (see the session delete button). Icon buttons grow to ~44px hit targets under `pointer-coarse:`. Form fields render at 16px below `sm` so iOS Safari doesn't auto-zoom on focus. In the chat input, Enter inserts a newline on coarse pointers (sending is the Send button's job there).
- **Popovers** — fixed pixel widths are clamped to the viewport (`Math.min(PANEL_WIDTH, innerWidth - padding)`), see `NotificationPanel` / `UserMenu` / `TableHeaderMenu` / `Select`. The **vertical** half of that fit is what the shared `useAnchoredPanel` hook (`hooks/useAnchoredPanel.ts`) exists for: it measures the trigger, opens the panel below it while that side has room and flips it above when it does not, and reports the `maxHeight` the chosen side allows so a long panel scrolls inside the viewport instead of hanging off its bottom edge. `ColumnPicker` and `Select` are placed by it; new anchored panels should use it rather than hand-writing a fifth copy of the same `getBoundingClientRect` math.

## Elevation & Depth

Depth comes from **opaque layers on hairlines**, with translucency kept for what floats.

- **Layer 0 (Canvas)** — `surface`, with `body::before` painting two still washes of light along its top edge. No animation, no film grain.
- **Layer 1 (Panel)** — `.glass-panel`: the opaque `panel` fill, a 1px `glass-border` hairline, and the shallowest of shadows. Tables, list cards, secondary buttons, the agent's bubble. A form field uses its own `.field-surface` — the same fill and shadow on the stronger `outline` border — which is what tells an editable field apart from the card it sits on and from a recessed read-only well. (It is a utility of its own because `glass-panel`'s `border` shorthand outranks a border-color class paired with it.)
- **Layer 2 (Raised)** — `.glass-panel-strong`: the opaque `panel-raised` fill with a soft drop shadow. Used for the chat input, admin form cards, `SectionCard`, and icon tiles.
- **Floating (Overlay)** — `.glass-panel-overlay`: the one content tier that is real glass, because it is the one tier with content underneath it — a ~90% fill, a 20px blur + 140% saturate, and the deep `--s-overlay` shadow. Only a tenth translucent on purpose: enough to take a tint from what it covers, never enough for a bright fill behind it to bleed into its text. Used for tooltips, dropdown/list menus (user menu, notification panel), and modal dialogs (`ConfirmDialog`, `RegistrySearchDialog`).
- **Chrome** — `.glass-chrome`: the edge-to-edge frame surfaces (app header, sidebars, timeline rail): the translucent `chrome` fill with a 12px blur, which lets the canvas's light through, and no border or shadow of its own — each call site draws only the single edge border (`border-b`/`border-r border-glass-border`) its layout needs.
- **Glow** — `shadow-glow` is a crisp 3px accent ring, not a halo. It marks hover and selection without spending the light the live edge is reserved for.

> **Note** — The utility names are historical: `glass-panel` and `glass-panel-strong` were frosted glass before the content tiers became opaque, and renaming them is a mechanical sweep of ~150 files that has not been done. The `backdrop-filter` blur on the two tiers that are still glass is applied through Tailwind's `backdrop-blur-*`/`backdrop-saturate-*` utilities via `@apply`, not a raw `backdrop-filter` declaration: Tailwind v4 composes `backdrop-filter` from `--tw-backdrop-*` custom properties and silently drops a bare declaration written inside an `@utility`.

## Shapes

The shape language is **crisp, lightly rounded**. The radius tokens are overridden in `@theme` (`--radius-xl`, `--radius-2xl`), so components keep Tailwind's class names while the whole scale sits one step sharper.

- **Panels & cards:** `0.75rem` (12px) radius (`rounded-2xl`).
- **Buttons & inputs:** `0.5rem` (8px) radius (`rounded-xl`).
- **Status badges & short constant labels:** `rounded-full` for pill shapes (`Badge`). Their text is a fixed vocabulary — `stdio`, `Super Admin`, `MCP` — so it always fits on one line and the pill never breaks.
- **Data chips carrying variable-length text** (a dependency task's title, a `server: tool` binding — `Chip`): `rounded-md`, a `max-w-64` cap, and one-line clipping with the full text in a hover tooltip. The cap is sized to clear a 30-character mono label — the title budget the design agent is held to — so a well-formed title fits whole and only a runaway one clips. A pill radius is *half the box height*, so the moment an arbitrary-length label wraps to a second line the curve swells and swallows the first and last lines' text. Capping the width and clipping is what keeps the shape honest; the lower radius is what stops the text from crowding the corner. A chip standing for a **dismissible selection** (the group and member chips a `RecordPickerField` renders, and the single secret chip on `SecretRefField`) carries a trailing remove button: a `size-5` round `lucide` `X` target, borderless and `on-surface-variant` at rest, taking an `error/40` outline and an `error/10` wash on hover and the standard `focus-visible:ring-2` — in `error/50` here, since removing an assignment is the same destructive verb `DeleteIconButton` speaks. It is hand-rolled rather than reusing `DeleteIconButton`/`ActionIconButton`, whose `size-8` and own `glass-panel` would stack a second glass tier inside a `text-xs` pill, and it stops at `pointer-coarse:size-7` rather than the usual ~44px touch target, which inside this pill would triple the chip's height. A chip standing for a **selectable option** (the tag grid in `TagPickerDialog`) instead makes the *whole* pill the control: the same shape on a `<button aria-pressed>` root, with the standard `focus-visible:ring-2 ring-accent/50` and a `motion-safe:active:scale-[0.97]` press. The two are mutually exclusive — a remove button cannot nest inside a button — and a pressed chip is marked twice over, by `.tag-chip-selected`'s stronger fill and by a leading 14px `Check`, because in a grid where every chip is already colored, a fill change alone is not a state anyone can read. A **row of chips inside a table cell** (`ChipRow` — the `Tags` column) wraps to at most two lines of `Chip`'s compact `xs` size: it shows as many chips as those two lines hold at the column's actual width and folds the rest into one neutral `+N` chip. That chip is a `<button>`: clicking it opens a modal `Dialog` (`size="md"`, `scrollable`) that lays out **every** chip in the row — not just the folded ones — as a wrapping grid, each carrying its own description-on-hover tooltip, which a hover panel could never host. The whole set rather than the leftovers, so the reader never has to merge what the dialog shows with what is still on the row. Left to wrap *freely*, a chip row would make row height a function of the data — a record with eight tags standing three lines tall beside a record with one — and hand the column its full max-content width at every other column's expense. Capping the wrap at two lines and dropping the chip to the `xs` size (11px mono, no vertical padding) holds every row at the height one `sm` line plus the cell padding kept before; the `Tags` column trims that padding (`py-1!`) and keeps its cells vertically centred so a lightly tagged row's one line sits mid-row like the text columns. The fit is measured from the rendered chips and redone whenever the column resizes, so narrowing the column raises `N` rather than widening the table. Only chips that fit *whole* are shown — a pill clipped mid-label names its tag no better than the count does, and letting it spill would push the count, the one mark saying there is more to see, out of the cell — so a column too narrow for even one whole chip on the first line shows the count alone. The folded chips are unmounted, so their labels are also handed to assistive technology in an `sr-only` span listing only those — a screen-reader user hears them without opening the dialog.
- **Active sidebar item indicator:** A 3px accent vertical bar on the left edge.

## Accessibility

- **Focus ring** — Every interactive element (buttons, inputs, textareas, selects, custom clickable elements) uses `focus-visible:ring-2 focus-visible:ring-accent/50` as its keyboard-focus treatment. This is already consistent across ~15 components (`components/ui/button.tsx`, `ThemeToggle.tsx`, `NotificationBell.tsx`, `UserMenu.tsx`, etc.) — reuse it rather than inventing a one-off focus style for a new component.
- **ARIA attributes** — Interactive or dynamically-updating elements carry appropriate `aria-label`, `aria-live`, and `role` (e.g. `role="menu"` for dropdowns) attributes. Purely decorative icons stay `aria-hidden` (see Iconography); an icon that carries standalone meaning gets a label instead.

## Components

- **Buttons:**
  - *Primary:* Solid `accent` fill, `on-primary` text, a faint inner-top highlight. Brightens on hover, dims on press.
  - *Secondary:* `glass-panel` background, on-surface text; accent text + accent border on hover.
  - *Ghost:* Transparent, on-surface-variant text; an ink wash + accent text on hover.
  - No variant moves on hover — a button lifts for nobody. `active:scale-[0.97]` is the only motion, and it answers a press.
  - *Submitting state:* Buttons that send a server request (Save, Sign in, Approve/Reject, Load more) pass a `status` to the shared `Button` and cycle their label through three stages — idle → `pendingLabel` → `doneLabel` (e.g. `Save → Saving… → Saved!`), reverting to idle ~2s after success. All three labels are stacked in one grid cell so the button **reserves the widest label's width and never reflows** — the same "reserve layout to avoid a swap-time jump" intent as the **Skeleton**. The hidden sizer copies are `aria-hidden` so the button keeps its visible label as its accessible name. State is driven by the `useAsyncAction` hook (see Motion → Patterns).
  - *Success (`done`) state:* While "Saved!" shows, the button turns **solid success-green** (`--color-success`, overriding the variant's fill) with a leading **checkmark** icon. Nothing moves: the color and the glyph are the whole message. It is held **non-interactive** (rendered `disabled`, but kept at full opacity) for the whole ~2s so a completed save cannot be re-triggered. `pending` is likewise non-interactive but keeps the standard dimmed `disabled` look. The `done` stage is **skipped** (`useAsyncAction({ showDone: false })`, and no `doneLabel`) whenever success takes the button off screen — a control that unmounts on completion (`AvatarField`'s Remove), or one whose success closes the surface it sits on (`AvatarDialog`'s Save and Upload, which hand the eye back to the avatar in the hero behind them). Celebrating on a button that is already sliding away reads as a stutter, not as feedback; the `pending` label still appears for a slow request either way.
- **Inputs / Textareas / Selects:** `field-surface` (the panel fill on the stronger `outline` border) with an accent ring on focus (`ring-accent/50`). 8px radius. Placeholder text uses `placeholder:text-on-surface-variant/50` — not the bare `on-surface-variant` token — so it stays visibly lighter than filled-in values (`text-on-surface`) instead of reading as near-identical secondary text. `Select`'s option list is not a native OS dropdown — it's a portaled `glass-panel-overlay` listbox rather than an unstyled system menu.
- **Read-only values (`DetailList` / `DetailItem`):** The only label/value treatment for read-only detail screens (a workflow execution, an approval, `/profile`, and every admin detail page's `AuditMeta` aside) — never hand-write a `dt`/`dd` pair. The label keeps `text-label`, identical to `FormField`'s label; the value sits on a **recessed field surface** below it: `outline-variant` border, `surface-dim/40` fill, `rounded-xl`, and a shallow inset shadow (`--inner-track-shadow`), with a `min-h-9` floor so a mono commit SHA and an em-dash placeholder hold the same height. Without a surface of its own a stack of bare label/value pairs reads as one undifferentiated column of text, and the eye cannot find where a pair ends. Giving the value a field restores `FormField`'s label/input rhythm, so a read-only page and an editable one share a skeleton (and the `FormSkeleton` placeholder, already a stack of `rounded-xl` bars, now matches what replaces it). The surface is **recessed, not raised**, for the same reason `SegmentedControl`'s track is: inverting the raised tiers is what stops it from being read as an editable input. The one attribute type that may leave the list is a **boolean account flag** (`enabled`, `emailVerified` on `/profile`): rendered as a `StatusPill` instead — a tinted `rounded-full` pill in `success` or `alert` carrying a `Check`/`TriangleAlert` glyph and naming the state it is actually in (`Enabled` / `Disabled`, `Email verified` / `Email not verified`). A label/value row spends a label and a full field on the word "Yes", which buries exactly the thing the reader is scanning for; the pill states it twice over, in tint and in glyph, so it survives grayscale and a glance. This is a promotion, not a duplication — a flag shown as a pill does not also appear in the list.
- **SectionCard:** The named container for a page section: `flex flex-col gap-5 rounded-2xl glass-panel-strong p-6` with a heading row of an accent icon tile (`h-9 w-9 rounded-xl glass-panel-strong text-accent`, static) and an `h2`. It reuses `AdminPageHeader`'s tile so a section heading reads as a quieter echo of the page heading above it rather than as a new shape. Reach for it whenever a page would otherwise stack several bare cards separated only by rules — a long read-only list splits far better into two named sections (`/profile`'s **Account** and **Access**) than into one undifferentiated column, because the headings tell the eye where one subject ends. It is also the shared home for the card class string the admin form pages currently hand-write; new cards should use the component rather than copy that string again.
- **ProfileHero:** `/profile`'s identity card, and the page's `h1`. A banner washed in the accent, fading out to the right and masked away downward, sits across the card's top, and the avatar — 120px inside a `rounded-full glass-panel-strong p-1` frame — straddles that edge. The heading is the **user's own name** (falling back to the username), with `Profile` demoted to a `text-label` line above it: the same rule detail pages follow in naming the record rather than the operation, and the largest type on the page should not be spent on a word every visitor already knows. Below it sit the `@handle` in the mono data face, the direct-role `Badge`s, and the account `StatusPill`s. **The avatar is the editor's only trigger** — a real `button` labelled "Edit avatar" that opens `AvatarDialog`, carrying a standing `Camera` badge on its lower-right edge and darkening under a full `Camera` scrim on hover and on keyboard focus. The badge, not the scrim, is what makes the avatar legible as editable on a touchscreen: this is the one hover-revealed control that must **not** fall back to `pointer-coarse:`, because Chrome reports a coarse pointer on hybrid touchscreen laptops and would pin a full-cover scrim open for mouse users, hiding the very thing it offers to edit. Making the avatar itself the control is what lets the page carry no editing chrome at all: the one editable thing is the one thing you can click.
- **SegmentedControl:** A `rounded-full` **recessed track** — `outline-variant` border, `surface-dim/40` fill, and an inset shadow (`--inner-track-shadow`) — deliberately the inverse of the raised tiers. Inputs and selects share the raised `field-surface`, so a raised pill sitting among form fields reads as a filled-in text field; the well is what tells the eye "this is a switch, and something slides inside it." The selected option is an accent pill that **springs** between segments (see Motion → Patterns) rather than cutting, and unselected segments wash to `accent-soft` on hover so they read as pressable rather than as static label text. An option may carry a leading `lucide` icon when the icon genuinely distinguishes the choices (Globe vs Terminal for an MCP server's transport) — never as decoration on every segment. Implemented as a `tablist` with roving `tabindex`: arrow keys, Home, and End move both the selection and the focus, and only the selected segment is a tab stop.
- **Data Tables:** Wrapped in a 12px-radius `glass-panel`, `border-collapse`. Header carries an ink wash (`glass-strong/70`) with a `divider` underline so it reads clearly apart from the body; its labels are sentence case at `text-xs font-medium`. Columns and rows are separated by `divider` grid lines (full strength in the header, `/60` in the body). Body rows are zebra-striped via the `even:` variant (`glass-strong/15`); hover overrides with an `accent-soft` wash. A row can also be **called out from elsewhere on the page** (`highlightedRowKey`): when a cell names another row — hovering a dependency chip in "Depends on" — that row takes an inset `ring-accent/50` plus a forced `accent-soft` fill (forced because the zebra stripe is a `:nth-child` rule and outranks a plain background utility). Every row carries its key as `data-row-key`, which is how such a reference finds its target. A list that uses this shows **all** its records rather than paginating — a callout is worthless if the row it points at is on another page. Each header cell carries a draggable resize strip on its right edge that tints `accent` on hover. A sortable/filterable column renders its whole header as a single full-width menu trigger (`TableHeaderMenu`) that opens a portaled glass dropdown (`glass-panel-overlay`, styled like the account menu's items) with labeled "Sort ascending" / "Sort descending" toggle actions and, below a divider, the column filter — a debounced text input or a select. The trigger carries its persistent state in a **single 16px indicator slot**, and that slot is absolutely positioned in the header cell's own right padding rather than laid out beside the label — so a sortable/filterable column is no wider than a plain one, and applying a filter cannot shift the label. It shows an accent `ArrowUp`/`ArrowDown` for the active sort direction, an accent `Funnel` when only a filter is applied, and a low-opacity `ChevronDown` when idle that strengthens on hover to signal the menu; a small accent dot rides along on whichever glyph is showing whenever a filter is applied, which is how a column that is both sorted and filtered says so with one glyph. Parking the slot outside the flow is deliberate: two inline icons plus their gaps used to add ~48px to every menu column's minimum width, which is dead space on a narrow column (`Enabled`, `Role`, `Tags`) whose header is short and whose cells are narrower still. It stays a child of the trigger button, so clicking the icon still opens the menu — and it stops short of the cell's resize strip, which sits above it and would otherwise take those clicks and show a `col-resize` cursor over the icon. By default every text cell clips to one line with an overflow tooltip; columns rendering interactive or multi-line content opt out. Column widths are measured from the natural layout once the rows arrive and then **fitted to the panel**, so the whole table — including the trailing actions column — always stays on screen. The fit is capped, not proportional: the text columns share a width ceiling that is lowered until they fit, so a column with width to burn (a long prompt, a repo URL) absorbs the shortfall while an already-narrow column is left alone rather than being squeezed until its own header clips. Action columns, which have no ellipsis to fall back on, keep their natural width — which is why a chip caps its own label width (see Shapes) rather than letting one long title claim the column. A column whose cell clips *itself* says so with `shrinkable` and rejoins the flexible set: a `ChipRow`'s `+N` fold is an ellipsis by another name, so the `Tags` column gives ground like a text column instead of squeezing every other one. Because such a cell measures *as it currently renders*, a natural width is measured once per column and cached for as long as the table lives: re-measuring a folded chip row on a column-set change would read back the width the last fit imposed, fold further, and measure narrower still, until the column sat on its header. Nothing drops below its own header content width (measured from a hidden nowrap sizer; 60px is the absolute fallback floor) — so header labels are never ellipsized, whether by the auto-fit or by drag-resizing. The fit is redone whenever the panel resizes. The panel scrolls horizontally only when the columns genuinely cannot fit, or after the user widens one by dragging — content is never clipped out of reach. While loading, the body shows shimmering **skeleton** rows that mirror the column layout (no spinner) so the table never reflows on data arrival.
- **Column picker:** Which columns a list table shows is the viewer's to choose, through a `Columns3` `HeaderIconButton` in the page header's action cluster (immediately after Refresh, sharing the round glass chrome so the two read as one toolbar). It opens the same portaled `glass-panel-overlay` dropdown the column header menu uses — right-aligned to its trigger since the trigger sits near the viewport's right edge, `snappy` transition — holding a `CheckboxGroup` (passed `flush`, so the group's own glass panel doesn't stack a second tier inside the overlay) under a `"Columns"` section label, then a divider and a "Reset to default" item. Toggling a column deliberately leaves the panel open. The section-label row also carries a **"Show all" / "Hide all"** bulk toggle, styled as a small text button rather than a full-width menu row so it reads as an action on all the columns rather than as one more column. **The panel is fitted to the viewport by `useAnchoredPanel`** (see Responsive & touch → Popovers): it flips above the trigger when the space below runs out, caps its height at what that side offers, and holds the label row and the reset action at its edges while only the checkbox list scrolls — a table with seventeen columns would otherwise hang its lower half off the bottom of a laptop screen, with the reset action unreachable. Past eight options the panel widens from 220px to 420px and the group switches to a **two-column grid**, halving how far that list scrolls; on a viewport too narrow to grant that width it folds back to one column on its own. Identifier and action columns are declared `visibility: "always"` and never appear in the list; a column too niche for the default view is declared `"optional"` and starts unchecked, which is how a table keeps its width for what matters. The choice persists per table in `localStorage`.
- **Assignment pickers:** A field that assigns records from an open-ended set never renders them inline — neither as a checkbox list nor as a `Select` that downloads the whole set. It shows the current selection as a row of removable **chips** (an em-dash `ReadOnlyField` when empty) under a `text-label` span, with a secondary "Select …" button below it opening `RecordPickerDialog`: the same `DataTable` + `useTableQuery` + `PaginationControls` trio the admin list pages use, so paging, per-column sort, and per-column filters are all server-side and the dialog behaves exactly like the list page for that resource. The draft lives in dialog state, so a record picked on the first page stays picked after the operator has paged past it; **Cancel** discards it and **Select** confirms. The dialog is mounted on first open and then kept mounted, so it costs no request until asked for. Its first column is a `Checkbox` when several records may be chosen and a `Radio` when only one may (`multiple={false}`) — a real radio group, so the browser enforces the "at most one" rule rather than leaving a set of checkboxes to mysteriously clear each other. The footer summarizes a multi-select as a count (`3 selected`) but a single-select **by name**, since "1 selected" tells an operator nothing they cannot already see; the name is read from the labels of every row seen so far, because the chosen row may have been paged away. The label field is deliberately a plain span rather than a `FormField`, whose `<label htmlFor>` would otherwise become the accessible name of the trigger button. A small, curated vocabulary is the exception: `TagPickerDialog` keeps the same outer contract but lays its options out as a wrapping grid of toggle chips filtered client-side, because the whole set is already in hand.
- **Skeleton:** Shimmering placeholder surface (`@utility skeleton`: a tinted `--skeleton-base` block with a brighter `--skeleton-sheen` band swept across by `--animate-shimmer`). Both tokens are theme-tuned so the shimmer reads clearly against light and dark panels. Used to reserve layout during data fetches — list rows, a detail page's form fields and its record-name title, and the workflow chat view — so content swaps in without jump or blank flash. Reduced-motion collapses it to a static block.
- **Status Badges:** Pill-shaped, gradient or glass per state.
- **Chat bubbles:** A session chat is one conversation several people and the agent post into (workflow executions, design sessions), so the thread reads on two axes at once: **which side** a bubble takes says whether it is *yours*, and **what surface** it wears says whether a human or the agent produced it. The viewer's own messages sit on the right with their avatar on the right edge; everyone else's — the agent's and the other participants' alike — sit on the left with theirs on the left edge. On that crowded left side the fill is what separates them: **humans are colored, the agent is a colorless panel.** The single-user chat (`/sessions/[sessionId]`) has one possible sender and renders no avatars, so it keeps the plain right-aligned layout throughout.
  - *User (own):* Solid `bubble` fill with `on-bubble` text (see Colors), asymmetric corner (`rounded-tr-md`, or `rounded-br-md` when an avatar sits beside it), inner-top highlight.
  - *User (another participant):* Left-aligned, `bg-secondary/12` over a `border-secondary/25` hairline, `rounded-bl-md` — a pale violet tint, so a human's message stays recognizable as one without competing with your own. Keeps the user bubble's `max-w-[75%]` rather than the assistant's full width.
  - *Assistant:* `glass-panel`, asymmetric corner (`rounded-tl-md`), accent-colored streaming caret. Content is rendered as **Markdown** (see Markdown content below). While streaming, the bubble carries the signature **live edge** (see Motion → Patterns).
  - *Reasoning ("thinking"):* `ReasoningBubble` — a dashed-border, italic panel (`bg-glass`, asymmetric `rounded-tl-md` corner like the assistant bubble) labelled with a 💭 "Thinking" header, rendering the agent's streamed reasoning text below the reply's normal weight and color. Renders nothing until reasoning text arrives. While the agent is still reasoning and hasn't started a reply yet, it carries the signature **live edge** in place of the generic "Agent is thinking…" pulse.
- **Code editor:** `CodeEditor` (`components/ui/code-editor.tsx`, CodeMirror 6) — the one control for editing source code, e.g. a script MCP server's **Source**. Editable, it sits on the same `field-surface` rounded-xl surface as `Textarea`, with an accent `focus-within` ring; read-only, it renders chrome-less inside a `ReadOnlyField as="div"`. Text is Geist Mono at 13px / 1.6. Syntax colors come from the `--c-code-*` tokens in `globals.css` (keyword → tag violet, string → tag mint, number → tag amber, constant → tag rose, function → tag cyan, type → tag teal, comment → `on-surface-variant` italic) — aliases of the tag palette, so they switch with the theme with no copy in the dark block. Lint marks are wavy text underlines: `error` for errors, `--c-code-warning` (amber) for warnings, `accent` for notes; hover tooltips and the autocomplete list use a `glass-strong` panel with an `outline` border.
- **Markdown content:** Agent-generated Markdown (assistant chat bubbles and the A2UI `Text` component) is rendered to HTML by `marked` and styled by the `markdown-body` utility (globals.css) — the single source of truth restoring what Tailwind preflight strips: heading scale (display face for h1/h2, tight tracking), list bullets, mono `code`/`pre` blocks on a `surface-container-high` tint with `overflow-x` scrolling, accent-colored links, `divider` rules, and outline-bordered tables, all sized to the 14px body scale.
- **A2UI surfaces:** An interactive surface in a session chat — an A2UI form, an `ApprovalControls` panel — follows the same side rule as the bubbles above once somebody has acted on it: answered by the viewer it moves to the right with their avatar on the right edge, answered by anyone else it stays left with theirs on the left. Until then nobody is attributed, no avatar shows, and it sits left as the agent's own output. `customCard` is rendered as `glass-panel-strong`. `customChoicePicker` chips take the solid accent fill when selected and `glass-panel` when not; a single-choice picker with five or more options drops the radio list and renders the shared `Select` instead, so its glass-panel trigger and portaled listbox are the ones documented under the form controls above. `customButton` labels take the shared `Button`'s per-variant text color (`on-primary`, `on-surface(-variant)`, `accent` on hover): a descendant selector (`[&_*]:!text-inherit`) makes whatever `buildChild` renders inside (typically a nested `Text`, which otherwise keeps its own color class) inherit the Button's color, so `ghost` and `secondary` stay readable on the light theme's transparent and near-white fills.
- **Theme Toggle:** A 36×36 round panel button in the app header. Sun/Moon SVG icons; takes accent text and the accent ring on hover. Icons cross-fade with a 90° rotation on toggle.
- **EmptyState:** Centered placeholder for empty regions (no messages, no rows, no sessions). Pairs an accent icon inside a raised tile with an optional title and description; the title is set in the display face. Has a `compact` variant for tight containers (session sidebar, table empty cell). See `@/components/ui/empty-state.tsx`.
- **Route loading/error boundaries:** Every route segment has a `loading.tsx` built from the same shared skeleton the page's own post-mount loading state uses (`FormSkeleton`, `AdminListSkeleton`, `WorkflowSessionSkeleton`, `ChatPanelSkeleton`) so the Suspense fallback and the page's own loading state are visually identical. Shells with persistent chrome (root, `(admin)`, `(chat)`, `/profile`) each have an `error.tsx` built on `RouteErrorFallback` (`EmptyState` + `Button reset`) so a render crash doesn't unmount the section's sidebar/header; `global-error.tsx` is the last-resort fallback for a crash in the root layout itself. A single root `not-found.tsx` handles unmatched URLs.

### Iconography

Icons come from [`lucide-react`](https://lucide.dev) (stroke icons, `strokeWidth={1.8}` to match the app's hand-drawn glyphs, `currentColor` for theme tinting). `AnimatedIcon` (`@/components/ui/animated-icon.tsx`) renders an icon in that stroke style and is static by default; its one animation is `wiggle`, a `motion-safe`-gated one-shot shake reserved for an error state's icon. Decorative icons are `aria-hidden` by default — add a label when an icon carries standalone meaning. Admin page headers pass an `icon` to `AdminPageHeader` (and lists pass the matching `emptyIcon` to `DataTable`) so each section reads at a glance; both are static. A detail page keeps its section's icon next to the record name, which is what ties the page back to the list it came from once the title no longer names the section.

## Motion

Motion follows a **Material You — "emphasized, gentle"** model: short durations, an emphasized easing curve for entrances, and React Spring physics for anything that mounts or unmounts. The intent is responsive without being chatty — every user action gets a small acknowledgement, never a long ceremony — and **nothing moves at rest**: a loop on screen means work is in flight (the live edge, the streaming caret, a skeleton, a pending action's icon).

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
- **Modal** — `ConfirmDialog` cross-fades the backdrop and `scale(0.94)→1` the body with a gentle spring. The scrim carries only a trace `backdrop-blur-[2px]` — the frosted look comes from the panel's own `glass-panel-overlay` blur, so the scrim stays light enough that the page behind the dialog is still legible and colorful content remains available for the panel to refract.
- **Buttons** — All variants share `active:scale-[0.97]` for tactile press feedback (`motion-safe`-guarded) and do not move on hover. Server-submitting buttons additionally use **optimistic UI** via `useAsyncAction`: the button disables immediately on click (preventing double-submits), and the `pending` label ("Saving…") only appears if the response takes longer than 200ms — fast responses skip straight to the `done` label, so quick saves never flash a transient "Saving…". On success the button stays non-interactive and confirms with a green fill and a checkmark (see Components → Buttons → Success state). The label width is fixed (see Components → Buttons) so none of these transitions reflow the button.
- **Sliding selection indicator** — The admin sidebar's and session list's 3px active bar and `SegmentedControl`'s selection pill are one mechanism: `useSlidingIndicator` (`@/hooks/useSlidingIndicator`) measures the active item with `getBoundingClientRect`, springs `offset` and `size` along a single axis (`vertical` for the bars, `horizontal` for the pill), re-measures under a `ResizeObserver`, and applies the first position `immediate` so nothing animates in on mount. Any new "highlight that follows the selection" reuses the hook — never re-implement the measurement.
- **Live edge (signature)** — While an agent is streaming (assistant bubble), a tool is running (`ToolActivityBubble`'s pill), the agent is still reasoning with no reply text yet (`ReasoningBubble`'s panel), or the agent is working with nothing else on screen yet (`WorkingIndicator`'s "Agent is thinking…" pill), the `live-edge` utility sends a comet of accent light around the panel's border: a conic gradient whose `from` angle (`@property --live-angle`) rotates via the `live-sweep` keyframes (2.4s linear), masked down to a thin ring on an overlay pseudo-element. Outside the chat it marks the same thing on the admin side: the workflow detail page's status bar (`app/(admin)/workflows/[workflowId]/page.tsx`) carries it while `publish` runs the description summarizer and while the workflow is still `generating`, the same page's Generated prompt field carries it while `generatePrompt` re-summarizes the design conversation, the Generate Workflow dialog panel carries it while the design run is being handed off, and the design session's `PromptDiffDialog` (`app/workflows/[workflowId]/design-session/page.tsx`) carries it — showing a placeholder skeleton in place of the diff — from the moment "Generate description" is triggered until the summary lands. The rule for adding a carrier is one thing only: **a generative-AI run is actually in flight behind that surface.** This is the one place the UI spends continuous motion and it means "the flow is live", so never apply it decoratively to idle surfaces (a workflow row that merely sits in an in-progress state keeps its calmer accent tint instead). For a surface driven by `useAsyncAction`, gate it on `status === "pending"`, not `inFlight` — that reuses the 200ms optimistic-UI delay described under **Buttons** above, so a fast response or a fast rejection never flashes the light. The one exception is `PromptDiffDialog`'s `loading`: it gates on `inFlight` instead, because during that 200ms window the dialog's `generated`/`description` props are still last render's stale (often empty) values, so a `pending`-gated skeleton would let a misleading "no diff" message flash through before the skeleton ever appears. Reduced-motion swaps the sweep for a static translucent accent ring.
- **Streaming caret** — Assistant bubble caret uses both `animate-blink` (the original step-start blink, preserved for tests) and `motion-safe:animate-pulse-cursor` (a softer opacity + scaleY pulse) so motion-safe users get the richer effect.
- **Theme toggle** — Sun/Moon icons cross-fade with a 90° rotation via `useTransition`.
- **Icons at rest** — Icons do not loop. The only icon animations are in-flight indicators on a pending action (`rocket-launch`, `spin-y`) and the one-shot `wiggle` on an error state's icon. An idle header, an empty table and an unread bell all hold still: the unread count badge says what the wiggle used to.

### Reduced motion

`@media (prefers-reduced-motion: reduce)` collapses every animation/transition to ~0ms in `globals.css`. React Spring code paths also call `useMotionConfig`, which detects the same preference and returns `{ duration: 0 }` so lifecycle callbacks still fire. Never assume animations will run — code defensively around their completion.
