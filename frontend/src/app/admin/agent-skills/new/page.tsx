/** @module NewAgentSkillPage — Admin form for creating a new agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Wand2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import {
  AgentSkillFields,
  type AgentSkillFormValues,
  agentSkillFormSchema,
  emptyAgentSkillFormValues,
  toAgentSkillCreateBody,
} from "@/components/admin/agent-skill-fields";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createAgentSkill } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

export default function NewAgentSkillPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(agentSkillFormSchema),
    mode: "onBlur",
    defaultValues: emptyAgentSkillFormValues(),
  });

  async function onSubmit(values: AgentSkillFormValues) {
    try {
      await save.run(async () => {
        await createAgentSkill(toAgentSkillCreateBody(values));
        dispatch(showToast({ message: "Agent skill created" }));
        router.push("/admin/agent-skills");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Agent Skills", href: "/admin/agent-skills" },
    { label: "New" },
  ];

  // The list page hides the Add button for this viewer, so reaching the form at
  // all means a deep link; refuse it here rather than let the submit 403.
  if (!canEdit) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="New Agent Skill" icon={Wand2} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <AgentSkillFields
            register={register}
            control={control}
            errors={errors}
            showPlaceholders
          />

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push("/admin/agent-skills")}
            >
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
