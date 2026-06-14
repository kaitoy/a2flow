"use client";

import { animated, to, useTransition } from "@react-spring/web";
import {
  Children,
  cloneElement,
  type FocusEvent,
  type MouseEvent,
  type ReactElement,
  type Ref,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useMotionConfig } from "@/lib/motion";

/** Side of the trigger the tooltip should appear on. */
export type TooltipPlacement = "top" | "bottom" | "left" | "right";

interface TooltipProps {
  /** Text rendered inside the floating tooltip. */
  label: string;
  /** Side of the trigger the tooltip should appear on. Defaults to `top`. */
  placement?: TooltipPlacement;
  /** Hover delay before the tooltip becomes visible, in milliseconds. Defaults to `300`. */
  delay?: number;
  /** When true, render the child unchanged with no tooltip behavior. Defaults to `false`. */
  disabled?: boolean;
  /** Single element that acts as the hover/focus trigger. */
  children: ReactElement;
}

interface Coords {
  top: number;
  left: number;
  origin: string;
  slideX: number;
  slideY: number;
}

const GAP = 10;
const EDGE_PADDING = 8;

/**
 * Floating glass tooltip shown on hover or focus of its child element.
 *
 * Renders via a portal to `document.body` so it is never clipped by the
 * trigger's scroll container, and uses React Spring's `useTransition` to
 * animate the chip in and out with the project's `gentle` motion preset.
 */
export function Tooltip({
  label,
  placement = "top",
  delay = 300,
  disabled = false,
  children,
}: TooltipProps) {
  const triggerRef = useRef<HTMLElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const tooltipId = `tooltip-${useId()}`;
  const config = useMotionConfig("gentle");

  const computeCoords = useCallback((): Coords | null => {
    const trigger = triggerRef.current;
    if (!trigger) return null;
    const rect = trigger.getBoundingClientRect();
    const tw = tooltipRef.current?.offsetWidth ?? 0;
    const th = tooltipRef.current?.offsetHeight ?? 0;
    let top = 0;
    let left = 0;
    let origin = "center center";
    let slideX = 0;
    let slideY = 0;
    switch (placement) {
      case "top":
        top = rect.top - th - GAP;
        left = rect.left + rect.width / 2 - tw / 2;
        origin = "center bottom";
        slideY = 6;
        break;
      case "bottom":
        top = rect.bottom + GAP;
        left = rect.left + rect.width / 2 - tw / 2;
        origin = "center top";
        slideY = -6;
        break;
      case "left":
        top = rect.top + rect.height / 2 - th / 2;
        left = rect.left - tw - GAP;
        origin = "right center";
        slideX = 6;
        break;
      case "right":
        top = rect.top + rect.height / 2 - th / 2;
        left = rect.right + GAP;
        origin = "left center";
        slideX = -6;
        break;
    }
    // Clamp horizontally/vertically so the tooltip never spills off the
    // viewport edges. Only applies when we have a measured size.
    if (tw > 0) {
      left = Math.max(EDGE_PADDING, Math.min(left, window.innerWidth - tw - EDGE_PADDING));
    }
    if (th > 0) {
      top = Math.max(EDGE_PADDING, Math.min(top, window.innerHeight - th - EDGE_PADDING));
    }
    return { top, left, origin, slideX, slideY };
  }, [placement]);

  const show = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setCoords(computeCoords());
      setOpen(true);
    }, delay);
  }, [computeCoords, delay]);

  const hide = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setOpen(false);
  }, []);

  // Re-measure once the tooltip mounts (so it knows its real size), and
  // recompute on scroll/resize so it tracks the trigger.
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

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.92, slide: 1 },
    enter: { opacity: 1, scale: 1, slide: 0 },
    leave: { opacity: 0, scale: 0.96, slide: 0.5 },
    config,
  });

  const child = Children.only(children) as ReactElement<
    Record<string, unknown> & { ref?: Ref<HTMLElement> }
  >;
  const childProps = child.props;
  const childRef = childProps.ref;

  function attachRef(node: HTMLElement | null) {
    triggerRef.current = node;
    if (typeof childRef === "function") childRef(node);
    else if (childRef && typeof childRef === "object") {
      (childRef as { current: HTMLElement | null }).current = node;
    }
  }

  function compose<E>(original: unknown, ours: (e: E) => void) {
    return (e: E) => {
      if (typeof original === "function") (original as (e: E) => void)(e);
      ours(e);
    };
  }

  const existingDescribedBy =
    typeof childProps["aria-describedby"] === "string"
      ? (childProps["aria-describedby"] as string)
      : undefined;
  const describedBy = open
    ? [existingDescribedBy, tooltipId].filter(Boolean).join(" ")
    : existingDescribedBy;

  const enhancedChild = cloneElement(child, {
    ref: attachRef,
    onMouseEnter: compose<MouseEvent<HTMLElement>>(childProps.onMouseEnter, show),
    onMouseLeave: compose<MouseEvent<HTMLElement>>(childProps.onMouseLeave, hide),
    onFocus: compose<FocusEvent<HTMLElement>>(childProps.onFocus, show),
    onBlur: compose<FocusEvent<HTMLElement>>(childProps.onBlur, hide),
    "aria-describedby": describedBy,
  });

  // When disabled, behave as a transparent wrapper: no handlers, no portal.
  if (disabled) return children;

  return (
    <>
      {enhancedChild}
      {typeof document !== "undefined" &&
        createPortal(
          transitions(
            (style, item) =>
              item &&
              coords && (
                <animated.div
                  ref={tooltipRef}
                  role="tooltip"
                  id={tooltipId}
                  style={{
                    position: "fixed",
                    top: coords.top,
                    left: coords.left,
                    transformOrigin: coords.origin,
                    opacity: style.opacity,
                    transform: to([style.scale, style.slide], (s, sl) => {
                      const tx = coords.slideX * sl;
                      const ty = coords.slideY * sl;
                      return `translate(${tx}px, ${ty}px) scale(${s})`;
                    }),
                    pointerEvents: "none",
                    zIndex: 9999,
                    boxShadow: "var(--shadow-glass-lg), var(--shadow-glow)",
                  }}
                  className="glass-panel-overlay max-w-xs whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] leading-5 text-on-surface"
                >
                  {label}
                </animated.div>
              )
          ),
          document.body
        )}
    </>
  );
}
