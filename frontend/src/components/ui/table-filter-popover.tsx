/** @module TableFilterPopover — per-column filter control (funnel button + glass popover). */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMotionConfig } from "@/lib/motion";
import { Input } from "./input";
import { Select } from "./select";

/** A choice rendered in the filter's select variant. */
export interface FilterOption {
  /** Visible label. */
  label: string;
  /** Value submitted to {@link TableFilterPopoverProps.onChange}. */
  value: string;
}

/** Props for {@link TableFilterPopover}. */
interface TableFilterPopoverProps {
  /** Column header label, used for accessible naming. */
  label: string;
  /** Current filter value; empty string means no filter is applied. */
  value: string;
  /** Called with the new filter value (debounced for the text variant). */
  onChange: (value: string) => void;
  /** When provided, render a select of these options instead of a free-text input. */
  options?: FilterOption[];
}

const PANEL_WIDTH = 200;
const GAP = 6;
const EDGE_PADDING = 8;
const DEBOUNCE_MS = 300;

interface Coords {
  top: number;
  left: number;
}

/** Funnel glyph; filled accent tint when a filter is active. */
function FunnelIcon({ active }: { active: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={active ? "text-accent" : "text-on-surface-variant"}
    >
      <path d="M3 4h18l-7 8v6l-4 2v-8z" />
    </svg>
  );
}

/**
 * Column filter control: a funnel button that opens a floating glass popover
 * containing either a debounced text input or, when `options` are given, a
 * select. The popover renders through a portal so it is never clipped by the
 * table's overflow, and closes on outside click or Escape.
 */
export function TableFilterPopover({ label, value, onChange, options }: TableFilterPopoverProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const [draft, setDraft] = useState(value);
  const config = useMotionConfig("snappy");

  // Keep the draft in sync when the applied value changes from outside.
  useEffect(() => {
    setDraft(value);
  }, [value]);

  const computeCoords = useCallback((): Coords | null => {
    const anchor = buttonRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    const left = Math.max(
      EDGE_PADDING,
      Math.min(rect.left, window.innerWidth - PANEL_WIDTH - EDGE_PADDING)
    );
    return { top: rect.bottom + GAP, left };
  }, []);

  useEffect(() => {
    if (!open) return;
    setCoords(computeCoords());
    const onChangePos = () => setCoords(computeCoords());
    window.addEventListener("scroll", onChangePos, true);
    window.addEventListener("resize", onChangePos);
    return () => {
      window.removeEventListener("scroll", onChangePos, true);
      window.removeEventListener("resize", onChangePos);
    };
  }, [open, computeCoords]);

  // Move focus into the field once the popover has opened.
  useEffect(() => {
    if (!open || !coords) return;
    const raf = requestAnimationFrame(() => {
      const panel = document.getElementById("table-filter-popover");
      (panel?.querySelector("input, select") as HTMLElement | null)?.focus();
    });
    return () => cancelAnimationFrame(raf);
  }, [open, coords]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onPointer = (e: PointerEvent) => {
      const target = e.target as Node;
      if (buttonRef.current?.contains(target)) return;
      if (document.getElementById("table-filter-popover")?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  /** Update the text draft and debounce the committed value. */
  const onText = useCallback(
    (next: string) => {
      setDraft(next);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => onChange(next), DEBOUNCE_MS);
    },
    [onChange]
  );

  const transitions = useTransition(open, {
    from: { opacity: 0, y: -6 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: -6 },
    config,
  });

  const active = value !== "";

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`Filter ${label}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex cursor-pointer items-center rounded p-0.5 transition-colors hover:bg-accent-soft/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        <FunnelIcon active={active} />
      </button>
      {typeof document !== "undefined" &&
        createPortal(
          transitions(
            (style, isOpen) =>
              isOpen &&
              coords && (
                <animated.div
                  id="table-filter-popover"
                  role="dialog"
                  aria-label={`Filter ${label}`}
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
                  {options ? (
                    <Select value={value} onChange={(e) => onChange(e.target.value)}>
                      <option value="">All</option>
                      {options.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </Select>
                  ) : (
                    <Input
                      type="text"
                      placeholder={`Filter ${label}…`}
                      value={draft}
                      onChange={(e) => onText(e.target.value)}
                    />
                  )}
                </animated.div>
              )
          ),
          document.body
        )}
    </>
  );
}
