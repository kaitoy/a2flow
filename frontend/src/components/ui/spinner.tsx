/** Animated circular loading indicator. Size sm=16 px, md=24 px, lg=40 px. */
export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const dim = { sm: 16, md: 24, lg: 40 }[size];
  return (
    <svg
      width={dim}
      height={dim}
      viewBox="0 0 24 24"
      fill="none"
      className="animate-spin text-accent"
      aria-label="Loading"
      role="status"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="56.5"
        strokeDashoffset="0"
        opacity="0.2"
      />
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="14"
        strokeDashoffset="0"
      />
    </svg>
  );
}
