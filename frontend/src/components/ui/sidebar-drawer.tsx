"use client";

import { animated, useTransition } from "@react-spring/web";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";

/** Props for {@link SidebarDrawer}. */
export interface SidebarDrawerProps {
  /** Whether the drawer is open. */
  open: boolean;
  /** Called to close the drawer (scrim tap or Escape). */
  onClose: () => void;
  /** Accessible name announced for the drawer dialog. */
  label: string;
  /**
   * Sidebar content — typically the same component that renders as the
   * static desktop sidebar, so the two presentations cannot drift apart.
   */
  children: ReactNode;
}

/**
 * Mobile off-canvas drawer that slides a sidebar in from the left over a
 * dimmed scrim. Hidden entirely at the `md` breakpoint and above, where the
 * static sidebar takes over. Dismissal (Escape, scrim tap), focus trapping,
 * and focus restoration follow the shared {@link useDialogA11y} wiring used
 * by the app's modal dialogs.
 */
export function SidebarDrawer({ open, onClose, label, children }: SidebarDrawerProps) {
  const config = useMotionConfig();
  const transitions = useTransition(open, {
    from: { opacity: 0, x: -100 },
    enter: { opacity: 1, x: 0 },
    leave: { opacity: 0, x: -100 },
    config,
  });

  useDialogA11y({ open, onClose, panelId: "sidebar-drawer", closeOnOutsideClick: false });

  // Guard against SSR — createPortal needs document.body, which is not
  // available during Next.js prerendering.
  if (typeof document === "undefined") return null;

  return createPortal(
    transitions(
      (style, item) =>
        item && (
          <div className="fixed inset-0 z-50 md:hidden">
            <animated.button
              type="button"
              style={{ opacity: style.opacity }}
              className="absolute inset-0 bg-black/25 backdrop-blur-[2px] cursor-default"
              onClick={onClose}
              // Stop the scrim itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              tabIndex={-1}
              aria-hidden="true"
            />
            <animated.div
              id="sidebar-drawer"
              role="dialog"
              aria-modal="true"
              aria-label={label}
              tabIndex={-1}
              style={{
                opacity: style.opacity,
                transform: style.x.to((x) => `translateX(${x}%)`),
                boxShadow: "var(--shadow-glass-lg)",
              }}
              className="absolute inset-y-0 left-0 flex max-w-[85vw]"
            >
              {children}
            </animated.div>
          </div>
        )
    ),
    document.body
  );
}
