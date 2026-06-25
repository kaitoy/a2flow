/** @module Avatar — User avatar showing an uploaded image or a generated default. */
"use client";

import { humation1 } from "@humation/assets-humation-1";
import { Avatar as HumationAvatar } from "@humation/react";
import { useState } from "react";
import { avatarUrl, type User } from "@/lib/api";

/** The subset of user fields an {@link Avatar} needs to render. */
export type AvatarUser = Pick<User, "id" | "username" | "avatarUpdatedAt">;

/** Props for {@link Avatar}. */
interface AvatarProps {
  /** The user to depict, or `null` while the signed-in user is still loading. */
  user: AvatarUser | null;
  /** Rendered width/height in pixels. Defaults to 36. */
  size?: number;
  /** Optional extra classes merged onto the circular container. */
  className?: string;
}

/**
 * Circular user avatar.
 *
 * Renders the user's uploaded image when one exists (falling back to the
 * generated default if it fails to load), otherwise a deterministic
 * {@link https://github.com/humation-labs/humation | Humation} illustration
 * seeded from the username. While the user is still loading (`null`), a neutral
 * placeholder keeps the layout stable.
 */
export function Avatar({ user, size = 36, className }: AvatarProps) {
  const url = user ? avatarUrl(user) : null;
  // Track the specific URL whose image failed to load; comparing against the
  // current URL means a newly uploaded avatar (different URL) is retried without
  // an effect to reset the flag.
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  const cls = [
    "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  const style = { width: size, height: size } as const;

  if (!user) {
    return (
      <span className={cls} style={style} aria-hidden="true">
        <PlaceholderGlyph size={size} />
      </span>
    );
  }

  if (url && failedUrl !== url) {
    return (
      <span className={cls} style={style}>
        {/* biome-ignore lint/performance/noImgElement: the avatar is served from a dynamic API endpoint and needs an onError fallback to the generated default, which next/image cannot express. */}
        <img
          src={url}
          alt={`${user.username} avatar`}
          width={size}
          height={size}
          className="h-full w-full object-cover"
          onError={() => setFailedUrl(url)}
        />
      </span>
    );
  }

  // The generated avatar is decorative: a username or accessible control label
  // always accompanies it (table cell, menu text, button aria-label), so it is
  // left without an SVG <title> to avoid duplicating that text.
  return (
    <span className={cls} style={style}>
      <HumationAvatar assets={humation1} seed={user.username} size={size} />
    </span>
  );
}

/** Neutral outline glyph shown while the user is still loading. */
function PlaceholderGlyph({ size }: { size: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width={size * 0.5}
      height={size * 0.5}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}
