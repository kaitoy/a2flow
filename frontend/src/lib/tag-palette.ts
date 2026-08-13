/**
 * @module tag-palette — maps a tag's stored palette slot to the classes that draw it.
 *
 * The backend stores a slot name (`TagColor`), never a color value, so the
 * palette can be retuned and can differ between light and dark without
 * rewriting rows. The values themselves are CSS custom properties in
 * `globals.css` (`--c-tag-*`, defined once per theme); everything here is the
 * one-line class that selects a slot.
 *
 * Unlike `avatar-palette.ts`, which hands literal hex values to a generative
 * art library and is therefore theme-independent, a tag chip sits on a glass
 * surface and needs contrast in both themes — so slots resolve to classes, not
 * colors.
 */

import type { TagColor } from "./api";

/**
 * Class that binds `--tag-color` for one palette slot.
 *
 * Combine with `tag-chip` (a chip's fill, border, and text) or `tag-swatch`
 * (a solid dot), both defined in `globals.css`.
 */
export const TAG_COLOR_CLASS: Record<TagColor, string> = {
  mint: "tag-mint",
  teal: "tag-teal",
  cyan: "tag-cyan",
  indigo: "tag-indigo",
  violet: "tag-violet",
  rose: "tag-rose",
  amber: "tag-amber",
  slate: "tag-slate",
};

/** Every palette slot, in the order pickers should offer them. */
export const TAG_COLORS = Object.keys(TAG_COLOR_CLASS) as TagColor[];

/** Slot assigned to a new tag when the user picks nothing. Matches the backend default. */
export const DEFAULT_TAG_COLOR: TagColor = "slate";

/**
 * Narrow a tag's color to a definite slot.
 *
 * The backend always sends one, but the field carries a default and so is
 * optional in the generated schema. Rather than spread that `undefined` through
 * every consumer, resolve it once to the same slot the backend would have
 * assigned.
 *
 * @param color - The color as read off a tag.
 * @returns The slot to draw with.
 */
export function resolveTagColor(color: TagColor | undefined): TagColor {
  return color ?? DEFAULT_TAG_COLOR;
}

/**
 * Human-readable name of a palette slot, for a color picker's option label.
 *
 * @param color - The palette slot.
 * @returns The slot name with its first letter capitalized.
 */
export function tagColorLabel(color: TagColor): string {
  return color.charAt(0).toUpperCase() + color.slice(1);
}
