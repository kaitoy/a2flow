/** @module UserMenu — Account dropdown showing the signed-in user and a logout action. */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { useRouter } from "next/navigation";
import { type RefObject, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { formatUserName, logout, type User } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";
import { clearUser } from "@/store/authSlice";
import { useAppDispatch } from "@/store/hooks";

/** Props for {@link UserMenu}. */
interface UserMenuProps {
  /** The trigger element the menu anchors itself beneath. */
  anchorRef: RefObject<HTMLElement | null>;
  /** Whether the menu is open. */
  open: boolean;
  /** Called when the menu requests to close (outside click, Escape, or item click). */
  onClose: () => void;
  /** The signed-in user, or null when not authenticated. */
  user: User | null;
}

/** Width of the dropdown menu in pixels. */
const PANEL_WIDTH = 220;
const GAP = 10;
const EDGE_PADDING = 8;

interface Coords {
  top: number;
  left: number;
}

/**
 * Resolve the user's primary display name: the full name ("First Last") when
 * present, falling back to the username and finally the email.
 *
 * @param user - The signed-in user.
 * @returns The best available display name.
 */
function displayName(user: User): string {
  return formatUserName(user) || user.username || user.email;
}

/**
 * Floating account menu anchored beneath the toolbar profile button. Shows the
 * signed-in user's name and username and a logout action. Rendered via a portal
 * so it is never clipped by the header, and animated in/out with the project's
 * motion preset.
 */
export function UserMenu({ anchorRef, open, onClose, user }: UserMenuProps) {
  const dispatch = useAppDispatch();
  const router = useRouter();
  const [coords, setCoords] = useState<Coords | null>(null);
  const [pending, setPending] = useState(false);
  const config = useMotionConfig("snappy");

  const computeCoords = useCallback((): Coords | null => {
    const anchor = anchorRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    const left = Math.max(
      EDGE_PADDING,
      Math.min(rect.right - PANEL_WIDTH, window.innerWidth - PANEL_WIDTH - EDGE_PADDING)
    );
    return { top: rect.bottom + GAP, left };
  }, [anchorRef]);

  // Track the anchor position while open.
  useEffect(() => {
    if (!open) return;
    setCoords(computeCoords());
    const onChange = () => setCoords(computeCoords());
    window.addEventListener("scroll", onChange, true);
    window.addEventListener("resize", onChange);
    return () => {
      window.removeEventListener("scroll", onChange, true);
      window.removeEventListener("resize", onChange);
    };
  }, [open, computeCoords]);

  // Close on Escape or a click outside both the menu and its anchor.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Node;
      if (anchorRef.current?.contains(target)) return;
      const panel = document.getElementById("user-menu");
      if (panel?.contains(target)) return;
      onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open, onClose, anchorRef]);

  const onLogout = useCallback(async () => {
    setPending(true);
    try {
      await logout();
    } catch {
      // Even if the request fails, drop local auth state and leave.
    }
    dispatch(clearUser());
    onClose();
    router.replace("/login");
  }, [dispatch, router, onClose]);

  const transitions = useTransition(open, {
    from: { opacity: 0, y: -6 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: -6 },
    config,
  });

  if (typeof document === "undefined") return null;

  const fullName = user ? formatUserName(user) : "";

  return createPortal(
    transitions(
      (style, isOpen) =>
        isOpen &&
        coords && (
          <animated.div
            id="user-menu"
            role="menu"
            aria-label="Account menu"
            style={{
              position: "fixed",
              top: coords.top,
              left: coords.left,
              width: PANEL_WIDTH,
              opacity: style.opacity,
              transform: style.y.to((y) => `translateY(${y}px)`),
              zIndex: 9999,
              boxShadow: "var(--shadow-glass-lg), var(--shadow-glow)",
            }}
            className="glass-panel-overlay rounded-xl p-2 text-on-surface"
          >
            <div className="flex flex-col gap-0.5 px-3 py-2">
              {user ? (
                <>
                  <span className="truncate text-sm font-medium text-on-surface">
                    {displayName(user)}
                  </span>
                  {fullName && (
                    <span className="truncate text-xs text-on-surface-variant">
                      @{user.username}
                    </span>
                  )}
                </>
              ) : (
                <span className="text-sm text-on-surface-variant">Not signed in</span>
              )}
            </div>
            <div className="my-1 h-px bg-glass-border" />
            <button
              type="button"
              role="menuitem"
              onClick={onLogout}
              disabled={pending}
              className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Log out
            </button>
          </animated.div>
        )
    ),
    document.body
  );
}
