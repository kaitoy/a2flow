interface ErrorBannerProps {
  error: string | null;
}

export function ErrorBanner({ error }: ErrorBannerProps) {
  if (!error) return null;
  return (
    <div
      className={[
        "mb-4 flex items-start gap-2 rounded-xl border border-error/40",
        "bg-error-container px-4 py-3 text-sm text-on-error-container backdrop-blur-md",
      ].join(" ")}
      role="alert"
    >
      <span aria-hidden="true">⚠</span>
      <span>{error}</span>
    </div>
  );
}
