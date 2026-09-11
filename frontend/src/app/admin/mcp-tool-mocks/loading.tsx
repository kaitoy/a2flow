import { FlaskConical } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the tool mocks list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Tool Mocks" }]}
      icon={FlaskConical}
      title="Tool Mocks"
      addHref="/admin/mcp-tool-mocks/new"
      addLabel="+ Add tool mock"
      columns={["Name", "Tool", "Server", "Description", "Actions"]}
    />
  );
}
