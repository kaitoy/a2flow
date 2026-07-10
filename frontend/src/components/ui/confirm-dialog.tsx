import { animated, useTransition } from "@react-spring/web";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Modal confirmation dialog with focus trap, keyboard navigation, and backdrop. */
export function ConfirmDialog({
  open,
  title,
  description,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

  useDialogA11y({ open, onClose: onCancel, panelId: "confirm-dialog", closeOnOutsideClick: false });

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
              className="absolute inset-0 bg-black/25 backdrop-blur-sm cursor-default"
              onClick={onCancel}
              // Stop the backdrop itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              tabIndex={-1}
              aria-hidden="true"
            />
            <div className="relative flex items-center justify-center min-h-full p-4 pointer-events-none">
              <animated.div
                id="confirm-dialog"
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby="confirm-dialog-title"
                style={{
                  opacity: style.opacity,
                  transform: style.scale.to((s) => `scale(${s})`),
                }}
                className="glass-panel-overlay rounded-2xl p-6 max-w-sm w-full pointer-events-auto"
              >
                <h2
                  id="confirm-dialog-title"
                  className="mb-2 font-display text-lg font-semibold tracking-tight text-on-surface"
                >
                  {title}
                </h2>
                <p className="mb-6 text-sm text-on-surface-variant">{description}</p>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onClick={onCancel}>
                    Cancel
                  </Button>
                  <Button variant="danger" onClick={onConfirm}>
                    Delete
                  </Button>
                </div>
              </animated.div>
            </div>
          </div>
        )
    ),
    document.body
  );
}
