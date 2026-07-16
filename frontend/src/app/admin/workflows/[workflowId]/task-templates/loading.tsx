"use client";

import { ListTree } from "lucide-react";
import { useParams } from "next/navigation";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/**
 * Route loading fallback for the task templates list page. `loading.tsx`
 * receives no `params` prop, so the `workflowId` needed for the breadcrumb and
 * "add" link is read via `useParams`, matching the real page.
 */
export default function Loading() {
  const { workflowId } = useParams<{ workflowId: string }>();
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflows", href: "/admin/workflows" },
          { label: "Edit", href: `/admin/workflows/${workflowId}` },
          { label: "Task Templates" },
        ]}
      />
      <AdminPageHeader
        title="Task Templates"
        icon={ListTree}
        addHref={`/admin/workflows/${workflowId}/task-templates/new`}
        addLabel="+ Add template"
      />
      <AdminListSkeleton
        columns={["#", "Title", "Description", "Depends on", "Tools", "Actions"]}
      />
    </AdminPageContainer>
  );
}
