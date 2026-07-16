"use client";

import { ListTree } from "lucide-react";
import { AdminListSkeleton } from "@/components/admin/admin-list-skeleton";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";

/** Route loading fallback for the read-only workflow tasks list page. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Sessions", href: "/admin/workflow-sessions" },
          { label: "Workflow Tasks" },
        ]}
      />
      <AdminPageHeader title="Workflow Tasks" icon={ListTree} />
      <AdminListSkeleton columns={["#", "Title", "Description", "Depends on", "Tools", "Status"]} />
    </AdminPageContainer>
  );
}
