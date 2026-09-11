import { FlaskConical } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the tool-mock detail page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tool Mocks", href: "/admin/mcp-tool-mocks" }, { label: "…" }]}
      icon={FlaskConical}
      fields={4}
    />
  );
}
