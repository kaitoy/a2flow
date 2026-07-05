import { FullPageSpinner } from "@/components/ui/full-page-spinner";

/** Default route loading fallback, used while `/` redirects and by any segment without a more specific loading.tsx. */
export default function Loading() {
  return <FullPageSpinner />;
}
