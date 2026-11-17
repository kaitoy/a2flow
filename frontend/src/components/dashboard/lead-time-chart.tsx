/** @module LeadTimeChart — Daily average lead time as an area line. */
"use client";

import { type KeyboardEvent, type PointerEvent, useEffect, useId, useState } from "react";
import { useT } from "@/i18n/provider";
import type { LeadTimeBucket } from "@/lib/api";
import { formatDuration } from "@/lib/format-duration";

/** The plot's height before it is measured, and its floor afterwards. */
const MIN_HEIGHT = 200;
/** Room above the tallest point so its glow is not clipped. */
const HEADROOM = 1.15;
/** Above this many days the per-day dots would merge into a smear. */
const MAX_DOTS = 31;

/** Props for {@link LeadTimeChart}. */
export interface LeadTimeChartProps {
  /** One bucket per calendar day, oldest first, empty days included. */
  buckets: LeadTimeBucket[];
}

/**
 * The lead-time trend: one point per day a run finished, joined by a line that
 * draws itself in. On the console (the `console:` variant) the line also
 * glows and carries a travelling light. Days on which nothing finished have no
 * point — the line passes straight over them — and say so in the hover
 * readout.
 *
 * Hovering (or focusing the chart and pressing the arrow keys) moves a
 * crosshair day by day and shows that day's average and run count. The plot
 * fills whatever height its panel has and is drawn in real pixels, re-measured
 * on resize, because a stretched viewBox would distort the dashed strokes the
 * draw-in and the light are made of.
 */
export function LeadTimeChart({ buckets }: LeadTimeChartProps) {
  const t = useT();
  const gradientId = useId();
  // State rather than a ref: the plot only mounts once there is data to draw,
  // and the observer below has to start when it does.
  const [plot, setPlot] = useState<HTMLDivElement | null>(null);
  const [{ width, height }, setSize] = useState({ width: 600, height: MIN_HEIGHT });
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    if (!plot) return;
    const observer = new ResizeObserver(([entry]) => {
      // A zero width means "not laid out" (or a test DOM); keep the default.
      const { width: w, height: h } = entry.contentRect;
      if (w > 0) setSize({ width: w, height: Math.max(MIN_HEIGHT, h) });
    });
    observer.observe(plot);
    return () => observer.disconnect();
  }, [plot]);

  const last = buckets.length - 1;
  const peak = Math.max(1, ...buckets.map((b) => b.avgLeadTimeSeconds ?? 0)) * HEADROOM;
  const x = (i: number) => (last > 0 ? (i / last) * width : width / 2);
  const y = (seconds: number) => height - (seconds / peak) * height;
  const points = buckets.flatMap((b, i) =>
    b.avgLeadTimeSeconds == null ? [] : [{ x: x(i), y: y(b.avgLeadTimeSeconds) }]
  );

  if (points.length === 0) {
    return (
      <p className="flex h-[200px] items-center justify-center text-sm text-on-surface-variant">
        {t("dashboard.noRunsFinished")}
      </p>
    );
  }

  const line = points.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join("");
  const area = `${line}L${points[points.length - 1].x.toFixed(1)} ${height}L${points[0].x.toFixed(1)} ${height}Z`;
  // A zero-length subpath with a round cap paints a dot.
  const dots = points.map((p) => `M${p.x.toFixed(1)} ${p.y.toFixed(1)}h0`).join("");

  const day = new Intl.DateTimeFormat(t.locale, { month: "short", day: "numeric" });
  const hovered = hover == null ? null : buckets[hover];
  const readout = (bucket: LeadTimeBucket) =>
    [
      day.format(new Date(bucket.bucketStart)),
      bucket.avgLeadTimeSeconds == null
        ? t("dashboard.noRunsFinished")
        : `${formatDuration(bucket.avgLeadTimeSeconds, t.locale)}, ${t("dashboard.runsFinished", { count: bucket.count })}`,
    ].join(": ");

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    setHover(Math.round(ratio * last));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    event.preventDefault();
    setHover((current) => Math.min(last, Math.max(0, (current ?? last) + step)));
  };

  return (
    <div className="flex flex-1 flex-col">
      <div
        ref={setPlot}
        // A slider over the days: the arrow keys move the crosshair, and each
        // stop is announced through aria-valuetext.
        role="slider"
        aria-label={t("dashboard.leadTimeChartLabel")}
        aria-valuemin={0}
        aria-valuemax={last}
        aria-valuenow={hover ?? last}
        aria-valuetext={readout(buckets[hover ?? last])}
        tabIndex={0}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHover(null)}
        onKeyDown={onKeyDown}
        onBlur={() => setHover(null)}
        className="relative min-h-[200px] flex-1 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
      >
        <svg width={width} height={height} aria-hidden="true" className="absolute inset-0">
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="var(--color-accent)" stopOpacity="0.38" />
              <stop offset="1" stopColor="var(--color-accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0.25, 0.5, 0.75].map((f) => (
            <line
              key={f}
              x1="0"
              x2={width}
              y1={height * f}
              y2={height * f}
              stroke="var(--color-divider)"
              strokeDasharray="2 6"
            />
          ))}
          {points.length > 1 && <path d={area} fill={`url(#${gradientId})`} />}
          {/* Keyed on the day count so the line redraws when the range changes, not on every poll. */}
          <path
            key={buckets.length}
            d={line}
            pathLength="1"
            strokeDasharray="1"
            fill="none"
            stroke="var(--color-accent)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            className="animate-draw-in console:[filter:drop-shadow(0_0_6px_var(--color-accent))]"
          />
          {buckets.length <= MAX_DOTS && (
            <path
              d={dots}
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth="6"
              strokeLinecap="round"
            />
          )}
          {points.length > 1 && (
            <path
              d={line}
              pathLength="100"
              strokeDasharray="3 97"
              fill="none"
              stroke="var(--color-glass-highlight)"
              strokeWidth="3"
              strokeLinecap="round"
              className="hidden console:motion-safe:block console:animate-comet console:[filter:drop-shadow(0_0_8px_var(--color-glass-highlight))]"
            />
          )}
          {hover != null && (
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1="0"
              y2={height}
              stroke="var(--color-on-surface-variant)"
              strokeOpacity="0.6"
            />
          )}
        </svg>
        <span className="pointer-events-none absolute left-0 top-0 font-mono text-[11px] text-on-surface-variant">
          {formatDuration(peak, t.locale)}
        </span>
        {hovered && hover != null && (
          <div
            aria-hidden="true"
            className="glass-panel-overlay pointer-events-none absolute top-2 z-10 whitespace-nowrap rounded-lg px-3 py-2 text-xs"
            style={
              hover > last / 2
                ? { right: `calc(${100 - (hover / Math.max(1, last)) * 100}% + 10px)` }
                : { left: `calc(${(hover / Math.max(1, last)) * 100}% + 10px)` }
            }
          >
            <p className="text-on-surface-variant">{day.format(new Date(hovered.bucketStart))}</p>
            {hovered.avgLeadTimeSeconds == null ? (
              <p className="text-on-surface">{t("dashboard.noRunsFinished")}</p>
            ) : (
              <>
                <p className="font-mono text-base font-semibold text-on-surface">
                  {formatDuration(hovered.avgLeadTimeSeconds, t.locale)}
                </p>
                <p className="text-on-surface-variant">
                  {t("dashboard.runsFinished", { count: hovered.count })}
                </p>
              </>
            )}
          </div>
        )}
      </div>
      <div className="mt-2 flex justify-between font-mono text-[11px] text-on-surface-variant">
        <span>{day.format(new Date(buckets[0].bucketStart))}</span>
        <span>{day.format(new Date(buckets[last].bucketStart))}</span>
      </div>
    </div>
  );
}
