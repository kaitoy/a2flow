import { FullPageSpinner } from "@/components/ui/full-page-spinner";

/** Route loading fallback for the notifications page. */
export default function Loading() {
  return <FullPageSpinner className="h-full" />;
}
