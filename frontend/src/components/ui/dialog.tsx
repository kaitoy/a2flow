/**
 * @module Dialog — the shared modal shell every dialog in the app is built on.
 *
 * Collects what ConfirmDialog, RegistrySearchDialog,
 * GenerateWorkflowDialog, and DescriptionDiffDialog each used to
 * hand-write: a portal to `document.body`, a scrim that closes on click without
 * stealing focus, the fade/scale transition, the `useDialogA11y` focus trap, and
 * a labelled `role="dialog"` panel. Callers supply only their own body.
 */
"use client";

import { animated, useTransition } from "@react-spring/web";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";

/** Maximum width of the dialog panel. */
export type DialogSize = "sm" | "md" | "lg" | "xl";

/** Tailwind max-width utility per {@link DialogSize}. */
const SIZE_CLASS: Record<DialogSize, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-5xl",
};

/** Props for {@link Dialog}. */
export interface DialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called when the dialog requests to close (backdrop or Escape). */
  onClose: () => void;
  /** DOM id of the panel; its title element derives `${panelId}-title`. */
  panelId: string;
  /** Heading text, and the panel's accessible name. */
  title: string;
  /** Sentence rendered under the heading. */
  description?: string;
  /** Maximum panel width. Defaults to `"md"`. */
  size?: DialogSize;
  /** Cap the panel at 80vh and lay it out as a column so a body child can scroll. */
  scrollable?: boolean;
  /** Action row rendered below the body, right-aligned. */
  footer?: ReactNode;
  /** Extra classes merged onto the panel. */
  panelClassName?: string;
  /** The dialog body. */
  children?: ReactNode;
}

/**
 * Modal dialog with a backdrop, focus trap, Escape handling, and enter/leave
 * animation.
 *
 * Outside-click closing is handled by the backdrop button rather than
 * `useDialogA11y`'s pointerdown listener, so the two never race; the hook is
 * still what traps Tab, closes on Escape, and restores focus to the trigger.
 * The backdrop is `aria-hidden` — it is decorative, and every dialog offers its
 * own labelled way out.
 */
export function Dialog({
  open,
  onClose,
  panelId,
  title,
  description,
  size = "md",
  scrollable = false,
  footer,
  panelClassName,
  children,
}: DialogProps) {
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

  useDialogA11y({ open, onClose, panelId, closeOnOutsideClick: false });

  // Guard against SSR — createPortal needs document.body, which is not
  // available during Next.js prerendering.
  if (typeof document === "undefined") return null;

  return createPortal(
    transitions(
      (style, item) =>
        item && (
          <div className="fixed inset-0 z-50">
            <animated.button
              type="button"
              style={{ opacity: style.opacity }}
              className="absolute inset-0 h-full w-full cursor-default border-0 bg-black/25 backdrop-blur-[2px]"
              onClick={onClose}
              // Stop the backdrop itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              tabIndex={-1}
              aria-hidden="true"
            />
            <div className="relative flex min-h-full items-center justify-center p-4 pointer-events-none">
              <animated.div
                id={panelId}
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby={`${panelId}-title`}
                style={{
                  opacity: style.opacity,
                  transform: style.scale.to((s) => `scale(${s})`),
                }}
                className={[
                  "w-full rounded-2xl glass-panel-overlay p-6 pointer-events-auto",
                  SIZE_CLASS[size],
                  scrollable ? "flex max-h-[80vh] flex-col" : "",
                  panelClassName ?? "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <h2
                  id={`${panelId}-title`}
                  className={`font-display text-lg font-semibold tracking-tight text-on-surface ${
                    description ? "mb-1" : "mb-4"
                  }`}
                >
                  {title}
                </h2>
                {description && (
                  <p className="mb-4 text-sm text-on-surface-variant">{description}</p>
                )}
                {children}
                {footer && <div className="mt-4 flex items-center justify-end gap-2">{footer}</div>}
              </animated.div>
            </div>
          </div>
        )
    ),
    document.body
  );
}
