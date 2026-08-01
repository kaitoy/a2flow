import { Wand2 } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the edit-agent-skill page, matching its own post-mount `FormSkeleton`. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Agent Skills", href: "/admin/agent-skills" },
          { label: "Edit" },
        ]}
      />
      <FormLayout header={<AdminPageHeader title="Edit Agent Skill" icon={Wand2} />}>
        <FormSkeleton fields={4} />
      </FormLayout>
    </AdminPageContainer>
  );
}
