"use client";

import { ListTree } from "lucide-react";
import { useParams } from "next/navigation";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/**
 * Route-transition fallback for the edit-workflow-task page, matching its own
 * post-mount `FormSkeleton`. Reads `wsId` itself via `useParams` since
 * `loading.tsx` receives no `params` prop.
 */
export default function Loading() {
  const { wsId } = useParams<{ wsId: string }>();
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Sessions", href: "/admin/workflow-sessions" },
          { label: "Workflow Tasks", href: `/admin/workflow-sessions/${wsId}/workflow-tasks` },
          { label: "Edit" },
        ]}
      />
      <AdminPageHeader title="Edit Workflow Task" icon={ListTree} />
      <FormColumn>
        <FormSkeleton fields={6} />
      </FormColumn>
    </AdminPageContainer>
  );
}
