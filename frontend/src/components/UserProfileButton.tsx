/** @module UserProfileButton — Toolbar account button opening the user menu. */
"use client";

import { useCallback, useRef, useState } from "react";
import { useAppSelector } from "@/store/hooks";
import { UserMenu } from "./UserMenu";
import { Tooltip } from "./ui/tooltip";

/** Optional extra classes merged onto the profile button. */
interface UserProfileButtonProps {
  className?: string;
}

/**
 * Toolbar button showing a user glyph that opens the account menu.
 *
 * Reads the signed-in user from the Redux auth slice and toggles a
 * {@link UserMenu} dropdown anchored to the button. The button always renders so
 * the header layout stays stable while the user is still loading.
 */
export function UserProfileButton({ className }: UserProfileButtonProps) {
  const user = useAppSelector((s) => s.auth.user);
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  const toggle = useCallback(() => setOpen((v) => !v), []);
  const close = useCallback(() => setOpen(false), []);

  const cls = [
    "inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-full relative",
    "glass-panel text-on-surface",
    "transition-[transform,translate,scale,box-shadow,color,background-color] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)]",
    "hover:shadow-glow hover:text-accent motion-safe:hover:scale-105 motion-safe:active:scale-95",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <Tooltip label="Account" placement="bottom">
        <button
          ref={buttonRef}
          type="button"
          onClick={toggle}
          className={cls}
          aria-label="Account"
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <UserIcon />
        </button>
      </Tooltip>
      <UserMenu anchorRef={buttonRef} open={open} onClose={close} user={user} />
    </>
  );
}

/** Outline user glyph matching the toolbar's icon style. */
function UserIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      width="18"
      height="18"
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
