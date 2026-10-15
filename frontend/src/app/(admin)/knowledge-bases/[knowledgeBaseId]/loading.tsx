import { BookOpen } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the knowledge base detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Knowledge Bases", href: "/knowledge-bases" }, { label: "…" }]}
      icon={BookOpen}
      fields={2}
    />
  );
}
