import { KeyRound } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the secret detail page. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "Secrets", href: "/admin/secrets" }, { label: "…" }]}
      icon={KeyRound}
      fields={3}
    />
  );
}
