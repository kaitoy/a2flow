import { animated, useTransition } from "@react-spring/web";
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
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
  const dialogRef = useRef<HTMLDivElement>(null);
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusable = dialog.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    first?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onCancel();
        return;
      }
      if (e.key === "Tab") {
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last?.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first?.focus();
          }
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

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
              tabIndex={-1}
              aria-hidden="true"
            />
            <div className="relative flex items-center justify-center min-h-full p-4 pointer-events-none">
              <animated.div
                ref={dialogRef}
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
                  className="mb-2 text-lg font-semibold text-on-surface"
                >
                  {title}
                </h2>
                <p className="mb-6 text-sm text-on-surface-variant">{description}</p>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onClick={onCancel}>
                    Cancel
                  </Button>
                  <Button variant="secondary" onClick={onConfirm} className="text-error">
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
