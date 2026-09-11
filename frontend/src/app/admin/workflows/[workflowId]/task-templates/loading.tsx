"use client";

import { ListTree } from "lucide-react";
import { useParams } from "next/navigation";
import { AdminLoading } from "@/components/admin/admin-loading";

/**
 * Route loading fallback for the task templates list page. `loading.tsx`
 * receives no `params` prop, so the `workflowId` needed for the breadcrumb and
 * "add" link is read via `useParams`, matching the real page.
 */
export default function Loading() {
  const { workflowId } = useParams<{ workflowId: string }>();
  return (
    <AdminLoading
      crumbs={[
        { label: "Workflows", href: "/admin/workflows" },
        { label: "…", href: `/admin/workflows/${workflowId}` },
        { label: "Task Templates" },
      ]}
      icon={ListTree}
      title="Task Templates"
      addHref={`/admin/workflows/${workflowId}/task-templates/new`}
      addLabel="+ Add task"
      columns={["#", "Title", "Description", "Depends on", "Tools", "Actions"]}
    />
  );
}
