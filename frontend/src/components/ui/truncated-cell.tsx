/** @module TruncatedCell — single-line table cell that reveals its full text on hover when clipped. */
"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";
import { Tooltip } from "./tooltip";

/** Props for {@link TruncatedCell}. */
interface TruncatedCellProps {
  /** Cell content; its rendered text is used as the tooltip label when clipped. */
  children: ReactNode;
}

/**
 * Render table-cell content on a single line, clipped with an ellipsis, and show
 * a tooltip with the full text only when the content actually overflows.
 *
 * Overflow is measured from the rendered DOM (`scrollWidth > clientWidth`) and
 * re-measured via a `ResizeObserver`, so resizing the column toggles the tooltip
 * on or off correctly. The full text comes from the element's `textContent`.
 */
export function TruncatedCell({ children }: TruncatedCellProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  const [text, setText] = useState("");

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-measure when the rendered cell content changes
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      setOverflowing(el.scrollWidth > el.clientWidth);
      setText(el.textContent ?? "");
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [children]);

  return (
    <Tooltip label={text} disabled={!overflowing}>
      <span ref={ref} className="block truncate">
        {children}
      </span>
    </Tooltip>
  );
}
