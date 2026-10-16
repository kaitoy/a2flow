import { BookOpen } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the knowledge bases list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Knowledge Bases" }]}
      icon={BookOpen}
      title="Knowledge Bases"
      addHref="/knowledge-bases/new"
      addLabel="+ Add knowledge base"
      columns={["Name", "Description", "Actions"]}
    />
  );
}
