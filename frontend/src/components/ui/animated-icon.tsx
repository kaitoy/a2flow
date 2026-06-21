/** @module AnimatedIcon — lucide icon wrapper that applies a subtle, theme-aware looping animation. */
import type { LucideIcon } from "lucide-react";

/**
 * Named decorative animations backed by the `--animate-*` tokens registered in
 * `globals.css`. `"none"` renders a static icon.
 */
export type IconAnimation = "bob" | "breathe" | "spin-slow" | "spin-occasional" | "wiggle" | "none";

/** Maps an {@link IconAnimation} to its `motion-safe`-gated Tailwind animation utility. */
const ANIMATION_CLASS: Record<IconAnimation, string> = {
  bob: "motion-safe:animate-bob",
  breathe: "motion-safe:animate-breathe",
  "spin-slow": "motion-safe:animate-spin-slow",
  "spin-occasional": "motion-safe:animate-spin-occasional",
  wiggle: "motion-safe:animate-wiggle",
  none: "",
};

/** Props for {@link AnimatedIcon}. */
export interface AnimatedIconProps {
  /** The lucide icon component to render (e.g. `Sparkles`). */
  icon: LucideIcon;
  /** Which looping animation to apply. Defaults to `"bob"`. */
  animation?: IconAnimation;
  /** Icon edge length in pixels. Defaults to `24`. */
  size?: number;
  /** Extra classes merged onto the icon (color, sizing overrides, delays). */
  className?: string;
}

/**
 * Renders a lucide icon with a gentle, theme-aware animation.
 *
 * The icon inherits `currentColor` so callers tint it via text color utilities,
 * and stroke width matches the app's hand-drawn icon style. Continuous
 * animations are gated behind `motion-safe:`, and the global
 * `prefers-reduced-motion` rule collapses them entirely for users who opt out.
 * Decorative by default (`aria-hidden`), so wrap with a label if the icon
 * carries meaning on its own.
 */
export function AnimatedIcon({
  icon: Icon,
  animation = "bob",
  size = 24,
  className,
}: AnimatedIconProps) {
  const cls = [ANIMATION_CLASS[animation], className].filter(Boolean).join(" ");
  return <Icon size={size} strokeWidth={1.8} aria-hidden="true" className={cls || undefined} />;
}
