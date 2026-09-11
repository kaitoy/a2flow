import { FlaskConical } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-tool-mock page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tool Mocks", href: "/admin/mcp-tool-mocks" }, { label: "New" }]}
      icon={FlaskConical}
      title="New Tool Mock"
      fields={4}
      form="column"
    />
  );
}
