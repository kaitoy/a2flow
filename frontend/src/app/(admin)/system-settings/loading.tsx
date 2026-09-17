import { Settings2 } from "lucide-react";
import { AdminLoading } from "@/components/admin/admin-loading";

/** Route-transition fallback for the system settings page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminLoading
      crumbs={[{ label: "System Settings" }]}
      icon={Settings2}
      title="System Settings"
      fields={8}
    />
  );
}
