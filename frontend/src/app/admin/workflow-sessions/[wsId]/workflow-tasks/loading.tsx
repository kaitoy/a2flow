"use client";

import { ListTree } from "lucide-react";
import { useParams } from "next/navigation";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/**
 * Route loading fallback for the workflow tasks list page. `loading.tsx`
 * receives no `params` prop, so the `wsId` needed for the breadcrumb and
 * "add" link is read via `useParams`, matching the real page.
 */
export default function Loading() {
  const { wsId } = useParams<{ wsId: string }>();
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Sessions", href: "/admin/workflow-sessions" },
          { label: "Workflow Tasks" },
        ]}
      />
      <AdminPageHeader
        title="Workflow Tasks"
        icon={ListTree}
        addHref={`/admin/workflow-sessions/${wsId}/workflow-tasks/new`}
        addLabel="+ Add task"
      />
      <AdminListSkeleton
        columns={["#", "Title", "Description", "Depends on", "Tools", "Status", "Actions"]}
      />
    </AdminPageContainer>
  );
}
