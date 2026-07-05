import { WorkflowSessionSkeleton } from "@/components/WorkflowSessionSkeleton";

/**
 * Route loading fallback for a workflow session page. No intermediate layout
 * wraps this route, so the full chrome (task timeline + header + panel)
 * belongs here, matching the page's own post-mount loading branch.
 */
export default function Loading() {
  return <WorkflowSessionSkeleton />;
}
