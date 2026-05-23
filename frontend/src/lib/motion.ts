/**
 * Motion presets and helpers used by React Spring across the app.
 *
 * All entrance/exit/list animations should source their spring configuration
 * from this file so that the project's "Material You — emphasized, gentle"
 * feel stays consistent. Per-component overrides should be the exception.
 */

import { type SpringConfig, useReducedMotion } from "@react-spring/web";

/** Named spring presets — pick by intent, not by raw tension/friction. */
export const SPRINGS = {
  /** Default for entrance/exit and most surface motion. Calm, settles cleanly. */
  gentle: { tension: 220, friction: 28 } as const,
  /** Quicker response for taps and brief feedback. */
  snappy: { tension: 320, friction: 26 } as const,
  /** Slight overshoot for playful confirmations (use sparingly). */
  bouncy: { tension: 260, friction: 18 } as const,
} satisfies Record<string, SpringConfig>;

/** Name of one of the {@link SPRINGS} presets. */
export type SpringPreset = keyof typeof SPRINGS;

/**
 * Return a spring config honoring the user's `prefers-reduced-motion`
 * setting. When reduced motion is requested, the returned config collapses
 * to `duration: 0` so transitions complete instantly while still firing
 * their lifecycle callbacks.
 *
 * @param preset - Which named spring to use (defaults to `gentle`).
 */
export function useMotionConfig(preset: SpringPreset = "gentle"): SpringConfig {
  const reduce = useReducedMotion();
  if (reduce) {
    return { duration: 0 };
  }
  return SPRINGS[preset];
}
