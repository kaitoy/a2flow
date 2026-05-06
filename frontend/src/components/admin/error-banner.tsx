interface ErrorBannerProps {
  error: string | null;
}

export function ErrorBanner({ error }: ErrorBannerProps) {
  if (!error) return null;
  return (
    <div className="mb-4 rounded bg-error-container p-3 text-sm text-on-error-container">
      {error}
    </div>
  );
}
