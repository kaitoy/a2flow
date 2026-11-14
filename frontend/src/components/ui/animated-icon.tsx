/** @module AnimatedIcon — lucide icon wrapper in the app's stroke style, with an optional one-shot cue. */
import type { LucideIcon } from "lucide-react";

/**
 * Named icon animations backed by the `--animate-*` tokens registered in
 * `globals.css`. `"wiggle"` is a one-shot shake for an error state; `"none"`
 * renders a static icon. Nothing loops: an icon at rest stays at rest.
 */
export type IconAnimation = "wiggle" | "none";

/** Maps an {@link IconAnimation} to its `motion-safe`-gated Tailwind animation utility. */
const ANIMATION_CLASS: Record<IconAnimation, string> = {
  wiggle: "motion-safe:animate-wiggle",
  none: "",
};

/** Props for {@link AnimatedIcon}. */
export interface AnimatedIconProps {
  /** The lucide icon component to render (e.g. `Sparkles`). */
  icon: LucideIcon;
  /** Which animation to apply. Defaults to `"none"`. */
  animation?: IconAnimation;
  /** Icon edge length in pixels. Defaults to `24`. */
  size?: number;
  /** Extra classes merged onto the icon (color, sizing overrides, delays). */
  className?: string;
}

/**
 * Renders a lucide icon, optionally with a one-shot animation.
 *
 * The icon inherits `currentColor` so callers tint it via text color utilities,
 * and stroke width matches the app's hand-drawn icon style. The animation is
 * gated behind `motion-safe:`, and the global `prefers-reduced-motion` rule
 * collapses it entirely for users who opt out.
 * Decorative by default (`aria-hidden`), so wrap with a label if the icon
 * carries meaning on its own.
 */
export function AnimatedIcon({
  icon: Icon,
  animation = "none",
  size = 24,
  className,
}: AnimatedIconProps) {
  const cls = [ANIMATION_CLASS[animation], className].filter(Boolean).join(" ");
  return <Icon size={size} strokeWidth={1.8} aria-hidden="true" className={cls || undefined} />;
}
