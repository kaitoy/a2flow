/** @module Toaster — Global, top-center stack of transient toast notifications. */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useMotionConfig } from "@/lib/motion";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { dismissToast, type Toast } from "@/store/toastSlice";

/** How long a success toast stays on screen before auto-dismissing, in milliseconds. */
const AUTO_DISMISS_MS = 3500;

/**
 * A single toast card. A success toast owns its own auto-dismiss timer so it
 * disappears independently {@link AUTO_DISMISS_MS} after it mounts; an error
 * toast has no timer and stays until the user clicks its dismiss button.
 */
function ToastCard({ toast }: { toast: Toast }) {
  const dispatch = useAppDispatch();
  const isError = toast.variant === "error";

  useEffect(() => {
    if (isError) return;
    const timer = setTimeout(() => dispatch(dismissToast(toast.id)), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [dispatch, toast.id, isError]);

  return (
    <div
      className={[
        "flex items-center gap-2.5 rounded-xl px-4 py-3 text-sm",
        isError
          ? "justify-between border border-error/40 bg-error-container text-on-error-container shadow-glass-lg backdrop-blur-md"
          : "glass-panel-overlay border border-success/40 text-on-surface",
      ].join(" ")}
      role="status"
      aria-live="polite"
    >
      <span className="flex items-center gap-2.5">
        {isError ? (
          <span aria-hidden="true">⚠</span>
        ) : (
          <Check className="size-4 shrink-0 text-success" aria-hidden="true" />
        )}
        <span>{toast.message}</span>
      </span>
      {isError && (
        <button
          type="button"
          onClick={() => dispatch(dismissToast(toast.id))}
          className="cursor-pointer rounded-full px-2 leading-none text-on-error-container/70 transition-[transform,translate,scale,background-color,color] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)] hover:bg-error/15 hover:text-on-error-container motion-safe:hover:scale-110"
          aria-label="Dismiss"
        >
          ✕
        </button>
      )}
    </div>
  );
}

/**
 * Renders the global toast queue from the Redux `toast` slice as a fixed,
 * top-center stack. Mounted once near the app root so toasts survive
 * client-side navigation (e.g. a form page that enqueues a toast and then
 * routes to its list page). Entrance/exit are animated with React Spring and
 * honor `prefers-reduced-motion` via {@link useMotionConfig}.
 */
export function Toaster() {
  const items = useAppSelector((s) => s.toast.items);
  const config = useMotionConfig("snappy");
  const [mounted, setMounted] = useState(false);

  const transitions = useTransition(items, {
    keys: (t) => t.id,
    from: { opacity: 0, y: -16 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: -16 },
    config,
  });

  // Defer the portal to a post-mount effect so the first client render
  // matches the server render (both skip it), avoiding a hydration mismatch
  // — createPortal needs document.body, which isn't available during SSR.
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return createPortal(
    <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2">
      {transitions((style, item) => (
        <animated.div style={style} className="pointer-events-auto">
          <ToastCard toast={item} />
        </animated.div>
      ))}
    </div>,
    document.body
  );
}
