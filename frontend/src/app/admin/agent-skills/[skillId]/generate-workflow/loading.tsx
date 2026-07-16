import { Sparkles } from "lucide-react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormSkeleton } from "@/components/admin/form-skeleton";

/** Route-transition fallback for the generate-workflow form, matching its field count. */
export default function Loading() {
  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Agent Skills", href: "/admin/agent-skills" },
          { label: "Generate Workflow" },
        ]}
      />
      <AdminPageHeader title="Generate Workflow" icon={Sparkles} />
      <FormColumn>
        <FormSkeleton fields={2} />
      </FormColumn>
    </AdminPageContainer>
  );
}
