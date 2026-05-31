/** @module ChatErrorBanner — Dismissible inline error banner for chat routes. */

interface ChatErrorBannerProps {
  /** Error message to display; when null/empty the banner renders nothing. */
  error: string | null;
  /** Invoked when the user clicks the dismiss button. */
  onDismiss: () => void;
}

/**
 * Inline error banner shown above a chat conversation, with a dismiss button.
 *
 * Renders nothing when {@link ChatErrorBannerProps.error} is falsy, so callers can mount
 * it unconditionally. The dismiss button scales slightly on hover (motion-safe) to match
 * the icon-button hover treatment used elsewhere in the UI.
 */
export function ChatErrorBanner({ error, onDismiss }: ChatErrorBannerProps) {
  if (!error) return null;
  return (
    <div className="shrink-0 mx-4 mt-3 flex items-center justify-between gap-3 rounded-xl border border-error/40 bg-error-container px-4 py-2 text-sm text-on-error-container backdrop-blur-md">
      <span className="flex items-center gap-2">
        <span aria-hidden="true">⚠</span>
        {error}
      </span>
      <button
        type="button"
        onClick={onDismiss}
        className="cursor-pointer rounded-full px-2 leading-none text-on-error-container/70 transition-[transform,translate,scale,background-color,color] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)] hover:bg-error/15 hover:text-on-error-container motion-safe:hover:scale-110"
        aria-label="Dismiss error"
      >
        ✕
      </button>
    </div>
  );
}
