import { Spinner } from "@/components/ui/spinner";

/**
 * Centered {@link Spinner} filling its container. Matches the spinner-gate
 * convention already used while auth/user state resolves (e.g. `AccountPage`,
 * `AuthProvider`) — reused as a route's `loading.tsx` fallback where no more
 * specific skeleton exists.
 *
 * @param className - Sizing for the outer wrapper. Defaults to `"h-screen"`;
 * pass `"h-full"` when nested inside a layout's own sized container.
 */
export function FullPageSpinner({ className = "h-screen" }: { className?: string }) {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <Spinner size="lg" />
    </div>
  );
}
