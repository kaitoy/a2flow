/**
 * @module Select — glass-panel dropdown/listbox picker.
 *
 * Replaces a native `<select>`, whose OS-rendered option list cannot be
 * styled in any browser. This renders its own `glass-panel` trigger and a
 * portaled `glass-panel-overlay` listbox, following the same architecture
 * (portal + `useDialogA11y` + `@react-spring/web` transition) as the app's
 * other floating panels (see `UserMenu`, `TableHeaderMenu`).
 */
"use client";

import { animated, useTransition } from "@react-spring/web";
import { ChevronDown } from "lucide-react";
import { type KeyboardEvent, useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";

/** A choice offered by {@link Select}. */
export interface SelectOption {
  /** Value passed to {@link SelectProps.onChange} when this option is chosen. */
  value: string;
  /** Visible label, shown on the trigger when selected and in the option row. */
  label: string;
}

/** Props for {@link Select}. */
export interface SelectProps {
  /**
   * Available options, in display order. For a placeholder-style first
   * choice (e.g. "All", "Unassigned", "No tenants"), include a leading
   * `{ value: "", label: "…" }` entry.
   */
  options: SelectOption[];
  /** The selected option's value; should match one of `options[].value`. */
  value: string;
  /** Called with the newly chosen option's value. */
  onChange: (value: string) => void;
  /** Disables the trigger and blocks opening; closes the popup if already open. */
  disabled?: boolean;
  /** DOM id placed on the trigger button (e.g. for `<label htmlFor>` association). */
  id?: string;
  /** Accessible name for the trigger when there is no associated `<label>`. */
  "aria-label"?: string;
  /** Extra classes merged onto the trigger button. */
  className?: string;
}

const TRIGGER_BASE =
  "flex w-full items-center justify-between gap-2 rounded-xl glass-panel px-4 py-2.5 " +
  // text-base below sm keeps the font at 16px so iOS Safari doesn't auto-zoom on focus
  "text-base sm:text-sm text-on-surface " +
  "transition-all duration-150 " +
  "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus:border-accent " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

// Same hover/spacing treatment as the app's shared dropdown item styling (see
// UserMenu / table-header-menu.tsx ITEM_CLASSES), minus the focus-visible
// ring: option rows are not individually focusable (see the module doc
// comment), so that ring can never trigger.
const OPTION_CLASSES =
  "flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-glass";

const MIN_PANEL_WIDTH = 160;
const GAP = 6;
const EDGE_PADDING = 8;

interface Coords {
  top: number;
  left: number;
  width: number;
}

/**
 * Glass-panel dropdown/listbox picker. Renders a `glass-panel` trigger button
 * showing the selected option's label, and — on open — a portaled
 * `glass-panel-overlay` listbox positioned beneath it, sized to the
 * trigger's own measured width (clamped to the viewport with a floor)
 * rather than a fixed pixel constant, since a value-picker's popup should
 * match its control's width.
 *
 * The trigger carries `role="combobox"` / `aria-expanded` / `aria-controls`.
 * Once open, DOM focus moves into the listbox itself via the shared
 * `useDialogA11y` wiring every other popover in the app uses (portal +
 * focus trap + Escape + outside-click), which drives arrow-key navigation
 * through `aria-activedescendant` on the listbox rather than keeping focus
 * pinned to the trigger as the strictest ARIA APG "select-only combobox"
 * reference does — a deliberate trade-off favoring this app's uniform
 * popover architecture over textbook purity (the same trade-off
 * `TableHeaderMenu` makes for its own panel).
 */
export function Select({
  options,
  value,
  onChange,
  disabled = false,
  id,
  "aria-label": ariaLabel,
  className,
}: SelectProps) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const [highlighted, setHighlighted] = useState(0);
  const config = useMotionConfig("snappy");
  const panelId = `select-listbox-${useId()}`;

  const selectedIndex = options.findIndex((o) => o.value === value);
  const selectedLabel = selectedIndex >= 0 ? options[selectedIndex].label : "";

  const computeCoords = useCallback((): Coords | null => {
    const anchor = triggerRef.current;
    if (!anchor) return null;
    const rect = anchor.getBoundingClientRect();
    const width = Math.max(
      MIN_PANEL_WIDTH,
      Math.min(rect.width, window.innerWidth - EDGE_PADDING * 2)
    );
    const left = Math.max(
      EDGE_PADDING,
      Math.min(rect.left, window.innerWidth - width - EDGE_PADDING)
    );
    return { top: rect.bottom + GAP, left, width };
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

  useDialogA11y({
    open,
    onClose: () => setOpen(false),
    anchorRef: triggerRef,
    panelId,
    ready: coords !== null,
  });

  // Close if disabled while open (e.g. a role change mid-interaction).
  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  // Re-seed the highlight from the selected option each time the listbox
  // opens; arrow-key/hover navigation owns `highlighted` after that.
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally re-runs only on open, not on every selectedIndex change
  useEffect(() => {
    if (!open) return;
    setHighlighted(Math.max(selectedIndex, 0));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    document
      .getElementById(`${panelId}-option-${highlighted}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [open, highlighted, panelId]);

  /** Apply the option at `index` and close the listbox. */
  function commit(index: number) {
    const opt = options[index];
    if (!opt) return;
    onChange(opt.value);
    setOpen(false);
  }

  function onTriggerKeyDown(e: KeyboardEvent) {
    if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      setOpen(true);
    }
  }

  function onListboxKeyDown(e: KeyboardEvent) {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlighted((i) => Math.min(i + 1, options.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlighted((i) => Math.max(i - 1, 0));
        break;
      case "Home":
        e.preventDefault();
        setHighlighted(0);
        break;
      case "End":
        e.preventDefault();
        setHighlighted(options.length - 1);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        commit(highlighted);
        break;
      default:
        break;
    }
  }

  const transitions = useTransition(open, {
    from: { opacity: 0, y: -6 },
    enter: { opacity: 1, y: 0 },
    leave: { opacity: 0, y: -6 },
    config,
  });

  const triggerClassName = className ? `${TRIGGER_BASE} ${className}` : TRIGGER_BASE;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        id={id}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={onTriggerKeyDown}
        className={triggerClassName}
      >
        <span className="min-w-0 flex-1 truncate text-left">{selectedLabel}</span>
        <ChevronDown
          size={16}
          strokeWidth={1.8}
          aria-hidden="true"
          className={`shrink-0 text-on-surface-variant/70 transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {typeof document !== "undefined" &&
        createPortal(
          transitions(
            (style, isOpen) =>
              isOpen &&
              coords && (
                <animated.div
                  id={panelId}
                  role="listbox"
                  tabIndex={-1}
                  aria-label={ariaLabel}
                  aria-activedescendant={
                    options.length > 0 ? `${panelId}-option-${highlighted}` : undefined
                  }
                  onKeyDown={onListboxKeyDown}
                  style={{
                    position: "fixed",
                    top: coords.top,
                    left: coords.left,
                    width: coords.width,
                    opacity: style.opacity,
                    transform: style.y.to((y) => `translateY(${y}px)`),
                    zIndex: 9999,
                    boxShadow: "var(--shadow-glass-lg), var(--shadow-glow)",
                  }}
                  className="glass-panel-overlay max-h-60 overflow-y-auto rounded-xl p-2 text-on-surface"
                >
                  {options.map((opt, index) => (
                    // biome-ignore lint/a11y/useFocusableInteractive: intentionally not focusable — the listbox owns keyboard focus and drives highlighting via aria-activedescendant (roving-focus pattern), matching onListboxKeyDown above
                    // biome-ignore lint/a11y/useKeyWithClickEvents: keyboard selection is handled by the listbox's onKeyDown (Enter/Space), not per-option
                    <div
                      key={opt.value}
                      id={`${panelId}-option-${index}`}
                      role="option"
                      aria-selected={opt.value === value}
                      onClick={() => commit(index)}
                      onMouseEnter={() => setHighlighted(index)}
                      className={`${OPTION_CLASSES} ${
                        opt.value === value
                          ? "bg-accent-soft/40 text-accent"
                          : index === highlighted
                            ? "bg-glass"
                            : ""
                      }`}
                    >
                      {opt.label}
                    </div>
                  ))}
                </animated.div>
              )
          ),
          document.body
        )}
    </>
  );
}
