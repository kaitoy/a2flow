import { FullPageSpinner } from "@/components/ui/full-page-spinner";

/** Route loading fallback for the profile page, matching its own `if (!user)` spinner gate. */
export default function Loading() {
  return <FullPageSpinner className="h-full" />;
}
