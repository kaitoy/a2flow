---
name: A2Flow
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#3f4948'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#6f7978'
  outline-variant: '#bfc8c7'
  surface-tint: '#266866'
  primary: '#004645'
  on-primary: '#ffffff'
  primary-container: '#1a5f5d'
  on-primary-container: '#97d6d3'
  inverse-primary: '#92d2cf'
  secondary: '#006c49'
  on-secondary: '#ffffff'
  secondary-container: '#6cf8bb'
  on-secondary-container: '#00714d'
  tertiary: '#840010'
  on-tertiary: '#ffffff'
  tertiary-container: '#ad0d1c'
  on-tertiary-container: '#ffbab5'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#aeeeeb'
  primary-fixed-dim: '#92d2cf'
  on-primary-fixed: '#00201f'
  on-primary-fixed-variant: '#00504e'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
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
    letterSpacing: 0.05em
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
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.04em
  badge:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 12px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  container-padding: 2rem
  sidebar-width: 240px
  gutter: 1.5rem
  card-padding: 1.25rem
  stack-sm: 0.5rem
  stack-md: 1rem
---

## Brand & Style
The design system is engineered for high-stakes AI automation and enterprise data management. It evokes a sense of **Stability, Precision, and Intelligence**. The visual language is rooted in **Modern Corporate** aesthetics, utilizing a structured information architecture that prioritizes clarity and operational efficiency.

The personality is authoritative yet transparent, ensuring complex backend workflows are presented through a lens of extreme legibility. The aesthetic avoids unnecessary ornamentation, focusing instead on crisp boundaries, intentional whitespace, and a sophisticated color palette that signals a mature SaaS environment.

## Colors
The palette is led by a deep, authoritative teal that anchors the brand in reliability.

- **Primary Teal (#1a5f5d):** Used for primary actions, active sidebar states, and key brand elements.
- **Success Green (#10b981):** Specifically reserved for 'Completed' status badges and positive performance trends.
- **Alert Red (#ef4444):** High-visibility indicator for 'Failed' executions and critical system errors.
- **Cool Grays:** A systematic range of slates and blues are used for text hierarchy, borders, and UI backgrounds to maintain a "cool" professional temperature.
- **Data Visualization:** Use stepped opacities of the Primary Teal for bar charts to indicate progression or volume without introducing conflicting hues.

## Typography
This design system utilizes **Inter** exclusively to ensure maximum readability across dense data tables and technical logs.

- **Hierarchy:** Strong contrast between uppercase section labels and mixed-case body text helps users scan complex pages.
- **Data Density:** Tight line heights are used for data tables to maximize information visible above the fold, while larger headings provide "breathing room" in dashboard views.
- **Monospaced Content:** A dedicated mono-type style is used for "Live Execution Logs" to maintain character alignment in technical output.

## Layout & Spacing
The layout follows a **Fixed Sidebar + Fluid Content** model. The sidebar remains pinned to the left at 240px, while the main dashboard area expands to fill the viewport.

- **Grid:** A 12-column grid system is used within the content area.
- **Card Strategy:** Complex data is broken into discrete cards. Key metrics occupy 3 or 4 columns, while the primary "Execution Registry" table spans the full 12-column width.
- **Rhythm:** An 8px base unit governs all spacing, ensuring consistent vertical rhythm between headers, descriptions, and data visualizations.

## Elevation & Depth
Depth is achieved through **Low-contrast outlines** and **Tonal layering** rather than aggressive shadows.

- **Level 0 (Background):** The lightest cool gray (#f8fafc) creates a foundation for all elements.
- **Level 1 (Cards):** Pure white surfaces with a 1px solid border (#e2e8f0) and a very subtle, diffused shadow (y: 1px, blur: 3px, opacity: 0.05).
- **Level 2 (Active States/Modals):** Increased shadow depth to indicate interactivity or temporary overlay.
- **Navigation:** The sidebar uses a subtle tonal shift (#f1f5f9) to distinguish it from the workspace without requiring a hard border.

## Shapes
The shape language is "Soft Professional."

- **Cards & Primary Containers:** Use a 0.25rem (4px) or 0.5rem (8px) radius to maintain a modern feel without appearing overly playful or consumer-grade.
- **Buttons:** Match the 4px radius for a crisp, technical look.
- **Status Badges:** Utilize a more rounded "pill" shape (1rem+) to visually separate status indicators from structural UI elements like buttons or cards.
- **Progress Bars/Charts:** Rounded corners on bar chart tops (2px) soften the data visualization.

## Components
- **Buttons:**
  - *Primary:* Solid Teal background with white text.
  - *Secondary:* White background with 1px border and Teal text.
  - *Ghost:* No border, used for utility actions like "Support" or "Account."
- **Data Tables:** High-density rows with light border-bottoms. Header rows use `label-caps` typography with a subtle background tint.
- **Status Badges:** Small, pill-shaped components.
  - *Success:* Green background, white text.
  - *Failed:* Red background, white text.
- **Data Visualizations:** Bar charts should use the Primary Teal at varying opacities (e.g., 40%, 60%, 80%) to show historical data, with 100% teal for the current or most significant data point.
- **Execution Logs:** A dark-themed container (Deep Charcoal) for code/log output, providing a high-contrast "developer-friendly" zone within the light UI.
- **Search Bar:** A prominent top-level input with a light gray fill and magnifying glass icon, serving as the primary navigation tool for records.
