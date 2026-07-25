/** @module avatar-palette — Color palette fed to the generated (boring-avatars) avatar. */

import type { AvatarConfig } from "@/lib/api";

/**
 * Default palette for generated avatars, derived from the design-system accent
 * and secondary hues (see DESIGN.md). The renderer takes hex strings through a
 * JS prop and parses them to derive contrasting features, so these are literal
 * hex values rather than CSS custom properties, and one palette serves both the
 * light and dark themes.
 */
export const DEFAULT_AVATAR_PALETTE: readonly string[] = [
  "#16BFA9", // mint accent — matches --c-accent-rgb (22, 191, 169)
  "#0E8A7C", // deep teal — light-theme --c-accent, oklch(0.56 0.12 183)
  "#7F62D5", // violet — --c-secondary, oklch(0.58 0.17 292)
  "#A7E8DC", // pale mint
  "#CBD5E1", // slate neutral — sits with --c-outline / --c-surface-dim
];

/**
 * Resolve the palette a generated avatar should render with.
 *
 * @param config - The user's saved avatar customization, if any.
 * @returns The user's palette when they have saved a non-empty one, otherwise
 *   {@link DEFAULT_AVATAR_PALETTE}.
 */
export function avatarPalette(config: AvatarConfig | null | undefined): string[] {
  const colors = config?.colors;
  return colors && colors.length > 0 ? [...colors] : [...DEFAULT_AVATAR_PALETTE];
}
