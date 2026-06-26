/** @module AgentAvatar — Circular avatar marking a message as sent by the workflow agent. */
"use client";

import { Sparkles } from "lucide-react";

/** Props for {@link AgentAvatar}. */
interface AgentAvatarProps {
  /** Rendered width/height in pixels. Defaults to 28. */
  size?: number;
  /** Optional extra classes merged onto the circular container. */
  className?: string;
}

/**
 * Circular avatar representing the workflow agent beside its messages.
 *
 * Unlike {@link Avatar}, the agent is not a user and has no uploaded or
 * generated image; instead a sparkles glyph on the accent gradient (shared with
 * the user message bubble) marks the message as machine-authored. Pair it with a
 * {@link Tooltip} carrying the workflow or skill name to identify which agent is
 * speaking.
 */
export function AgentAvatar({ size = 28, className }: AgentAvatarProps) {
  const cls = [
    "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full",
    "bg-gradient-to-br from-accent to-secondary text-on-primary",
    "shadow-[0_8px_24px_-12px_var(--color-accent-soft),inset_0_1px_0_rgba(255,255,255,0.35)]",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={cls} style={{ width: size, height: size }} aria-hidden="true">
      <Sparkles size={Math.round(size * 0.5)} strokeWidth={2} />
    </span>
  );
}
