/** @module ErrorBanner — Shared inline error alert, optionally dismissible. */

interface ErrorBannerProps {
  /** Error message to display; renders nothing when null/empty. */
  error: string | null;
  /** When provided, renders a dismiss (✕) button that calls this on click. */
  onDismiss?: () => void;
}

/**
 * Inline error alert banner. Uses `animate-message-in` and `role="alert"` per
 * DESIGN.md's entrance-animation convention for error banners. Renders
 * nothing when `error` is falsy, so callers can mount it unconditionally.
 */
export function ErrorBanner({ error, onDismiss }: ErrorBannerProps) {
  if (!error) return null;
  return (
    <div
      className={[
        "flex items-start gap-2 rounded-xl border border-error/40",
        "bg-error-container px-4 py-3 text-sm text-on-error-container backdrop-blur-md",
        "animate-message-in",
        onDismiss ? "justify-between" : "",
      ].join(" ")}
      role="alert"
    >
      <span className="flex items-start gap-2">
        <span aria-hidden="true">⚠</span>
        <span>{error}</span>
      </span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="cursor-pointer rounded-full px-2 leading-none text-on-error-container/70 transition-[transform,translate,scale,background-color,color] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)] hover:bg-error/15 hover:text-on-error-container motion-safe:hover:scale-110"
          aria-label="Dismiss error"
        >
          ✕
        </button>
      )}
    </div>
  );
}
