/** @module UserProfileButton — Toolbar account button opening the user menu. */
"use client";

import { useCallback, useRef, useState } from "react";
import { useAppSelector } from "@/store/hooks";
import { UserMenu } from "./UserMenu";
import { Avatar } from "./ui/avatar";
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
    "inline-flex h-9 w-9 pointer-coarse:h-11 pointer-coarse:w-11 cursor-pointer items-center justify-center rounded-full relative",
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
          <Avatar user={user} size={36} />
        </button>
      </Tooltip>
      <UserMenu anchorRef={buttonRef} open={open} onClose={close} user={user} />
    </>
  );
}
