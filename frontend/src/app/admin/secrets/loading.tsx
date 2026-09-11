import { KeyRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route loading fallback for the secrets list page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Secrets" }]}
      icon={KeyRound}
      title="Secrets"
      addHref="/admin/secrets/new"
      addLabel="+ Add secret"
      columns={["Name", "Type", "Created At", "Actions"]}
    />
  );
}
