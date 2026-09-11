import { KeyRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the new-secret page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Secrets", href: "/admin/secrets" }, { label: "New" }]}
      icon={KeyRound}
      title="New Secret"
      fields={3}
      form="column"
    />
  );
}
