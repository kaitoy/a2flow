"use client";

import { Bell } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useNotifications } from "@/hooks/useNotifications";
import { useAppSelector } from "@/store/hooks";
import { NotificationPanel } from "./NotificationPanel";
import { Tooltip } from "./ui/tooltip";

/** Optional extra classes merged onto the bell button. */
interface NotificationBellProps {
  className?: string;
}

/**
 * Toolbar bell that opens the notification center.
 *
 * Drives notification polling via {@link useNotifications}, shows an unread-count
 * badge sourced from the Redux notifications slice, and toggles a
 * {@link NotificationPanel} dropdown anchored to the button.
 */
export function NotificationBell({ className }: NotificationBellProps) {
  useNotifications();
  const unreadCount = useAppSelector((s) => s.notifications.unreadCount);
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

  const label = unreadCount > 0 ? `Notifications (${unreadCount} unread)` : "Notifications";
  const badge = unreadCount > 99 ? "99+" : String(unreadCount);

  return (
    <>
      <Tooltip label={label} placement="bottom">
        <button
          ref={buttonRef}
          type="button"
          onClick={toggle}
          className={cls}
          aria-label={label}
          aria-haspopup="dialog"
          aria-expanded={open}
        >
          <Bell
            size={18}
            strokeWidth={1.8}
            aria-hidden="true"
            className={unreadCount > 0 ? "origin-top motion-safe:animate-attention" : undefined}
          />
          {unreadCount > 0 && (
            <span
              aria-hidden="true"
              className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-badge text-on-primary shadow-card"
            >
              {badge}
            </span>
          )}
        </button>
      </Tooltip>
      <NotificationPanel anchorRef={buttonRef} open={open} onClose={close} />
    </>
  );
}
