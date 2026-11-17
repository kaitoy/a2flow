/** @module KpiTile — One headline number on the dashboard. */
"use client";

import { animated, useSpring } from "@react-spring/web";
import type { LucideIcon } from "lucide-react";
import { type CSSProperties, type ReactNode, useId } from "react";
import { useT } from "@/i18n/provider";
import { useMotionConfig } from "@/lib/motion";

/** What a tile's tone says: all well, work in flight, worth a look, or wrong. */
export type KpiTone = "accent" | "run" | "warn" | "fail";

const TONE_COLOR: Record<KpiTone, string> = {
  accent: "var(--color-accent)",
  run: "var(--c-tag-cyan)",
  warn: "var(--c-tag-amber)",
  fail: "var(--color-error)",
};

/** Props for {@link KpiTile}. */
export interface KpiTileProps {
  /** What the number counts. */
  label: string;
  /** The number itself. */
  value: number;
  /** Icon shown beside the label, tinted with the tone. */
  icon: LucideIcon;
  /** Color of the tile's icon, sparkline and glow. Defaults to `"accent"`. */
  tone?: KpiTone;
  /** One supporting line under the number. */
  detail?: ReactNode;
  /** Past values, oldest first, drawn as a sparkline along the tile's lower edge. */
  history?: number[];
}

/**
 * A stat tile: a large figure that counts up to its value, a supporting line,
 * and a sparkline of how the value moved while the page has been open. On the
 * console (the `console:` variant) the figure also glows, and flares once
 * whenever the value changes.
 *
 * The digits stay in the ink color — only the icon, the sparkline and, on the
 * console, the light around the digits take the tone — so the tile reads the
 * same without color vision. The animated figure
 * is `aria-hidden`; the settled value is exposed in a visually hidden copy.
 */
export function KpiTile({
  label,
  value,
  icon: Icon,
  tone = "accent",
  detail,
  history = [],
}: KpiTileProps) {
  const t = useT();
  const config = useMotionConfig("gentle");
  const { shown } = useSpring({ from: { shown: 0 }, to: { shown: value }, config });
  const format = (n: number) => new Intl.NumberFormat(t.locale).format(Math.round(n));

  return (
    <section
      aria-label={label}
      className="console-panel flex min-w-0 flex-col gap-2 overflow-hidden p-4"
      style={{ "--glow": TONE_COLOR[tone] } as CSSProperties}
    >
      <header className="flex items-center gap-2">
        <Icon size={16} strokeWidth={1.8} aria-hidden="true" className="shrink-0 text-(--glow)" />
        <h2 className="truncate text-label">{label}</h2>
      </header>
      <p className="console:glow-text font-mono text-5xl font-semibold leading-none tracking-tight tabular-nums text-on-surface">
        <span className="sr-only">{format(value)}</span>
        {/* Keyed on the value so the flare replays on every change. */}
        <animated.span
          key={value}
          aria-hidden="true"
          className="inline-block console:motion-safe:animate-console-flash"
        >
          {shown.to(format)}
        </animated.span>
      </p>
      <div className="min-h-4 truncate text-xs text-on-surface-variant">{detail}</div>
      <Sparkline values={history} />
    </section>
  );
}

/**
 * The tile's trace: `values` scaled to fill a short strip that bleeds to the
 * tile's edges. With fewer than two samples it draws a flat baseline, so the
 * tile keeps its height from the first paint.
 */
function Sparkline({ values }: { values: number[] }) {
  const gradientId = useId();
  const width = 100;
  const height = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const points =
    values.length < 2
      ? [
          [0, height - 2],
          [width, height - 2],
        ]
      : values.map((v, i) => [
          (i / (values.length - 1)) * width,
          // Leave 2px above and below so the stroke is never clipped.
          span === 0 ? height / 2 : height - 2 - ((v - min) / span) * (height - 4),
        ]);
  const line = points
    .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`)
    .join("");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      className="-mx-4 -mb-4 h-10 w-[calc(100%+2rem)]"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--glow)" stopOpacity="0.32" />
          <stop offset="1" stopColor="var(--glow)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line}L${width} ${height}L0 ${height}Z`} fill={`url(#${gradientId})`} />
      <path
        d={line}
        fill="none"
        stroke="var(--glow)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
