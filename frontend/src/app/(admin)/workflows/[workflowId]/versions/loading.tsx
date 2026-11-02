"use client";

import { History } from "lucide-react";
import { useParams } from "next/navigation";
import { AdminLoading } from "@/components/admin/admin-loading";

/**
 * Route loading fallback for the version history page. `loading.tsx` receives
 * no `params` prop, so the `workflowId` for the breadcrumb is read via
 * `useParams`, matching the real page.
 */
export default function Loading() {
  const { workflowId } = useParams<{ workflowId: string }>();
  return (
    <AdminLoading
      crumbs={[
        { label: "Workflows", href: "/workflows" },
        { label: "…", href: `/workflows/${workflowId}` },
        { label: "Versions" },
      ]}
      icon={History}
      title="Version History"
      columns={["Version", "Name", "Description", "Actions"]}
    />
  );
}
