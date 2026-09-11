import { Tags } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the tags list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tags" }]}
      icon={Tags}
      title="Tags"
      addHref="/admin/tags/new"
      addLabel="+ Add tag"
      columns={["Name", "Preview", "Created At", "Actions"]}
    />
  );
}
