import { Tags } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the new tag form. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tags", href: "/admin/tags" }, { label: "New" }]}
      icon={Tags}
      title="New Tag"
      fields={2}
      form="column"
    />
  );
}
