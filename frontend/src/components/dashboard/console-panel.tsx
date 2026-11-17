/** @module ConsolePanel — The dashboard's ground, in either look, and the titled panels on it. */
"use client";

import { type ReactNode, type Ref, useId } from "react";
import type { DashboardLook } from "@/hooks/useDashboardLook";

/** Props for {@link ConsolePanel}. */
export interface ConsolePanelProps {
  /** The panel's heading. */
  title: string;
  /** One line under the heading saying what the panel measures. */
  hint?: string;
  /** Content pinned to the header's right edge: a headline figure or a control. */
  aside?: ReactNode;
  /** The chart itself. */
  children: ReactNode;
  /** Extra classes for the panel, typically its grid span. */
  className?: string;
}

/**
 * A dashboard panel with a heading row. Shared by every chart on `/dashboard`
 * so their titles, hints, and right-hand figures line up; only meaningful
 * inside a {@link ConsoleFrame}, which supplies the series colors and decides
 * whether the panel is a plain card or a lit instrument.
 */
export function ConsolePanel({ title, hint, aside, children, className }: ConsolePanelProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={["console-panel flex min-w-0 flex-col gap-4 p-5", className]
        .filter(Boolean)
        .join(" ")}
    >
      {/* Wraps: in a narrow panel the aside drops under the title instead of squeezing it. */}
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-40 flex-1">
          <h2
            id={headingId}
            className="font-display text-lg font-semibold tracking-tight text-on-surface"
          >
            {title}
          </h2>
          {hint && <p className="mt-0.5 text-xs text-on-surface-variant">{hint}</p>}
        </div>
        {aside && <div className="shrink-0">{aside}</div>}
      </header>
      {children}
    </section>
  );
}

/** Props for {@link ConsoleFrame}. */
export interface ConsoleFrameProps {
  /** The dashboard's contents: its header, tiles, and panels. */
  children: ReactNode;
  /** Which of the dashboard's two looks to draw. Defaults to `"standard"`. */
  look?: DashboardLook;
  /** Reaches the dashboard root, the element the page sends full screen. */
  ref?: Ref<HTMLDivElement>;
}

/**
 * The dashboard root, in one of two looks.
 *
 * `"standard"` is the app's own ground and follows the viewer's theme, like
 * every other screen. `"console"` is Mission Control: the dark gridded ground,
 * with `data-theme="dark"` pinned on the root so the console — and every token
 * resolved inside it — is dark whichever theme the rest of the app is in. The
 * `console` class is also what the `console:` variant keys on, so everything
 * inside that glows or loops does so only in that look.
 *
 * Either way the root carries `dashboard`, which supplies the chart series
 * colors, and is a container, so the layout inside reflows by the room the
 * dashboard actually has rather than by the viewport.
 */
export function ConsoleFrame({ children, look = "standard", ref }: ConsoleFrameProps) {
  const isConsole = look === "console";
  return (
    <div
      ref={ref}
      data-theme={isConsole ? "dark" : undefined}
      // The standard look paints its own ground only so that full screen,
      // which shows the root alone, is not left on the browser's black.
      className={`dashboard min-h-full overflow-y-auto ${isConsole ? "console" : "bg-surface"}`}
    >
      <div className="@container mx-auto flex max-w-[100rem] flex-col gap-4 p-4 sm:p-6">
        {children}
      </div>
    </div>
  );
}
