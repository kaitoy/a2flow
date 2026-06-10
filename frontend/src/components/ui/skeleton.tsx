/**
 * Shimmering placeholder block used to reserve layout while data loads.
 *
 * The caller supplies the size and shape through `className` (e.g.
 * `"h-4 w-32"`); the component only contributes the shimmer surface and a
 * default rounded corner. It is `aria-hidden` because it conveys no content —
 * announce loading via an `aria-busy`/`role="status"` container around groups
 * of skeletons instead.
 *
 * @param className - Tailwind classes controlling width, height, and shape.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={["block skeleton rounded-md", className].filter(Boolean).join(" ")}
    />
  );
}
