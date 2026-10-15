import { BookOpen } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-knowledge-base page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Knowledge Bases", href: "/knowledge-bases" }, { label: "New" }]}
      icon={BookOpen}
      title="New Knowledge Base"
      fields={2}
      form="column"
    />
  );
}
