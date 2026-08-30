import { ShieldCheck } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the tool-invocation audit list. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Audit Logs", href: "/admin/audit" },
          { label: "Tool Invocations" },
        ]}
      />
      <AdminPageHeader title="Tool Invocations" icon={ShieldCheck} />
      <AdminListSkeleton
        columns={[
          "Tool",
          "Server",
          "Decision",
          "Denial Reason",
          "Workflow Execution",
          "Created At",
        ]}
      />
    </AdminPageContainer>
  );
}
