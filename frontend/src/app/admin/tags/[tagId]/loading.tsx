import { Tags } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the tag detail page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tags", href: "/admin/tags" }, { label: "…" }]}
      icon={Tags}
      fields={2}
    />
  );
}
