/** @module NewWorkflowTaskTemplatePage — Admin form for adding a task template to a workflow. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ListTree } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { McpToolPicker } from "@/components/admin/mcp-tool-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zWorkflowTaskTemplateCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import {
  createWorkflowTaskTemplate,
  listWorkflowTaskTemplates,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import { toBindings } from "@/lib/mcp-tool-options";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the title/description constraints. The parent
// workflow id comes from the URL, and the form edits dependencies and tool
// bindings as plain string arrays (encoded values), so omit those and re-add
// them in the form's shape. `inputApprovalExempt` is the checkbox-group half of
// the tool picker — a subset of `toolBindings` — folded back into the bindings
// on submit by `toBindings`.
const schema = zWorkflowTaskTemplateCreate
  .omit({
    workflowId: true,
    dependsOnIds: true,
    toolBindings: true,
  })
  .extend({
    dependsOnIds: z.array(z.string()),
    toolBindings: z.array(z.string()),
    inputApprovalExempt: z.array(z.string()),
  });

type FormValues = z.infer<typeof schema>;

/** Form page that adds a new task template to the workflow in the URL. */
export default function NewWorkflowTaskTemplatePage() {
  const t = useT();
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const [candidates, setCandidates] = useState<WorkflowTaskTemplate[]>([]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      title: "",
      description: "",
      dependsOnIds: [] as string[],
      toolBindings: [] as string[],
      inputApprovalExempt: [] as string[],
    },
  });

  useEffect(() => {
    // Nothing to pick from when the form is refused below.
    if (!canEdit) return;
    listWorkflowTaskTemplates(workflowId, { limit: 100 })
      .then(setCandidates)
      .catch(() => {
        // Candidate list is non-essential; the picker simply renders empty.
      });
  }, [workflowId, canEdit]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await createWorkflowTaskTemplate({
          workflowId,
          title: values.title,
          description: values.description || null,
          dependsOnIds: values.dependsOnIds,
          toolBindings: toBindings(values.toolBindings, values.inputApprovalExempt),
        });
        dispatch(showToast({ message: t("workflows.templateCreated") }));
        router.push(`/workflows/${workflowId}/task-templates`);
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: t("common.home"), href: "/" },
    { label: t("common.workflows"), href: "/workflows" },
    { label: t("workflows.taskTemplates"), href: `/workflows/${workflowId}/task-templates` },
    { label: t("common.new") },
  ];

  // The template list hides its Add button for this viewer, so reaching the form
  // at all means a deep link; refuse it here rather than let the submit 403.
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
      <AdminPageHeader title={t("workflows.newTaskTemplate")} icon={ListTree} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField
            htmlFor="title"
            label={t("common.title")}
            required
            error={errors.title?.message}
          >
            <Input
              id="title"
              placeholder={t("workflows.shortActionableTitle")}
              {...register("title")}
            />
          </FormField>

          <FormField htmlFor="description" label={t("common.description")}>
            <Textarea
              id="description"
              rows={4}
              placeholder={t("workflows.longerFormDetailsOptional")}
              {...register("description")}
            />
          </FormField>

          <FormField htmlFor="dependsOnIds" label={t("common.dependsOn")}>
            <Controller
              control={control}
              name="dependsOnIds"
              render={({ field }) => (
                <CheckboxGroup
                  name="dependsOnIds"
                  options={candidates.map((t) => ({ value: t.id, label: t.title }))}
                  value={field.value}
                  onChange={field.onChange}
                  emptyMessage={t("workflows.noOtherTemplatesInThisWorkflowYet")}
                />
              )}
            />
          </FormField>

          <FormField htmlFor="toolBindings" label={t("workflows.mcpTools")}>
            <Controller
              control={control}
              name="toolBindings"
              render={({ field: tools }) => (
                <Controller
                  control={control}
                  name="inputApprovalExempt"
                  render={({ field: exempt }) => (
                    <McpToolPicker
                      value={tools.value}
                      onChange={tools.onChange}
                      exempt={exempt.value}
                      onExemptChange={exempt.onChange}
                    />
                  )}
                />
              )}
            />
          </FormField>

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel={t("common.saving")}
            >
              {t("common.save")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push(`/workflows/${workflowId}/task-templates`)}
            >
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
