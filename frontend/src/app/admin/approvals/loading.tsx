import { CheckCircle2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the approvals list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Approvals" }]}
      icon={CheckCircle2}
      title="Approvals"
      columns={[
        "Title",
        "Status",
        "Approver",
        "Decided By",
        "Comment",
        "Session",
        "Created At",
        "Description",
        "Decided At",
      ]}
    />
  );
}
