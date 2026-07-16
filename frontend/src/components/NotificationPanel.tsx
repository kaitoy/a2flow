"use client";

import { animated, useTransition } from "@react-spring/web";
import { X } from "lucide-react";
import { useRouter } from "next/navigation";
import { type RefObject, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { deleteNotification, markAllNotificationsRead, markNotificationRead } from "@/lib/api";
import logger from "@/lib/logger";
import { useMotionConfig } from "@/lib/motion";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { markAllReadLocal, markReadLocal, removeLocal } from "@/store/notificationsSlice";
import { Button } from "./ui/button";
import { formatFullTimestamp } from "./ui/date-time";
import { Tooltip } from "./ui/tooltip";

/** Props for {@link NotificationPanel}. */
interface NotificationPanelProps {
  /** The trigger element the panel anchors itself beneath. */
  anchorRef: RefObject<HTMLElement | null>;
  /** Whether the panel is open. */
  open: boolean;
  /** Called when the panel requests to close (outside click, Escape, or item click). */
  onClose: () => void;
}

/** Width of the dropdown panel in pixels. */
const PANEL_WIDTH = 340;
const GAP = 10;
const EDGE_PADDING = 8;

interface Coords {
  top: number;
  left: number;
}

/** Format an ISO timestamp as a short relative time such as "5m ago" or "2d ago". */
function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

/**
 * Floating dropdown listing the current user's notifications, anchored beneath the
 * toolbar bell. Each row deep-links to the workflow session it concerns and is
 * marked read on click. Rendered via a portal so it is never clipped by the
 * header, and animated in/out with the project's motion preset.
 */
export function NotificationPanel({ anchorRef, open, onClose }: NotificationPanelProps) {
  const dispatch = useAppDispatch();
  const router = useRouter();
  const items = useAppSelector((s) => s.notifications.items);
  const unreadCount = useAppSelector((s) => s.notifications.unreadCount);
  const [coords, setCoords] = useState<Coords | null>(null);
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

  useDialogA11y({
    open,
    onClose,
    anchorRef,
    panelId: "notification-panel",
    ready: coords !== null,
  });

  const onSelect = useCallback(
    (
      id: string,
      workflowSessionId: string | null | undefined,
      workflowId: string | null | undefined
    ) => {
      dispatch(markReadLocal(id));
      markNotificationRead(id).catch((err) => {
        logger.error({ err, id }, "failed to mark notification read");
      });
      onClose();
      // Run-scoped notifications (approvals, completion) deep-link to the
      // session chat; workflow-scoped ones (a generated draft) to the workflow.
      if (workflowSessionId) {
        router.push(`/workflow-sessions/${encodeURIComponent(workflowSessionId)}`);
      } else if (workflowId) {
        router.push(`/admin/workflows/${encodeURIComponent(workflowId)}`);
      }
    },
    [dispatch, router, onClose]
  );

  const onDismiss = useCallback(
    (id: string) => {
      dispatch(removeLocal(id));
      deleteNotification(id).catch((err) => {
        logger.error({ err, id }, "failed to delete notification");
      });
    },
    [dispatch]
  );

  const onMarkAllRead = useCallback(() => {
    dispatch(markAllReadLocal());
    markAllNotificationsRead().catch((err) => {
      logger.error({ err }, "failed to mark all notifications read");
    });
  }, [dispatch]);

  const transitions = useTransition(open, {
    from: { opacity: 0, y: -6 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: -6 },
    config,
  });

  if (typeof document === "undefined") return null;

  return createPortal(
    transitions(
      (style, isOpen) =>
        isOpen &&
        coords && (
          <animated.div
            id="notification-panel"
            role="dialog"
            tabIndex={-1}
            aria-label="Notifications"
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
            className="glass-panel-overlay max-h-[70vh] overflow-y-auto rounded-xl p-2 text-on-surface"
          >
            <div className="flex items-center justify-between gap-2 px-2 py-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
                Notifications
              </span>
              {unreadCount > 0 && (
                <Button variant="ghost" onClick={onMarkAllRead}>
                  Mark all read
                </Button>
              )}
            </div>
            {items.length === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-on-surface-variant">
                No notifications
              </div>
            ) : (
              <ul className="flex flex-col gap-1">
                {items.map((n) => (
                  <li key={n.id} className="flex items-start gap-1">
                    <button
                      type="button"
                      onClick={() => onSelect(n.id, n.workflowSessionId, n.workflowId)}
                      className="flex min-w-0 flex-1 items-start gap-2 rounded-lg px-3 py-2 text-left transition-colors duration-150 hover:bg-glass focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                    >
                      <span
                        aria-hidden="true"
                        className={[
                          "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                          n.read ? "bg-transparent" : "bg-accent",
                        ].join(" ")}
                      />
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="truncate text-sm font-medium text-on-surface">
                          {n.title}
                        </span>
                        {n.body && (
                          <span className="line-clamp-2 text-xs text-on-surface-variant">
                            {n.body}
                          </span>
                        )}
                        <Tooltip label={formatFullTimestamp(n.createdAt)} placement="bottom">
                          <span className="w-fit text-[11px] text-on-surface-variant">
                            {formatRelativeTime(n.createdAt)}
                          </span>
                        </Tooltip>
                      </span>
                    </button>
                    <span className="shrink-0 pt-2">
                      <ActionIconButton icon={X} label="Dismiss" onClick={() => onDismiss(n.id)} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </animated.div>
        )
    ),
    document.body
  );
}
