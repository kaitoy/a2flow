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
import { Button } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zWorkflowTaskTemplateCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  createWorkflowTaskTemplate,
  listWorkflowTaskTemplates,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import { loadMcpToolOptions, type McpToolOption, valueToBinding } from "@/lib/mcp-tool-options";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the title/description constraints. The parent
// workflow id comes from the URL, and the form edits dependencies and tool
// bindings as plain string arrays (encoded values), so omit those and re-add
// them in the form's shape. Position is coerced from the number input.
const schema = zWorkflowTaskTemplateCreate
  .omit({
    workflowId: true,
    position: true,
    dependsOnIds: true,
    toolBindings: true,
  })
  .extend({
    position: z.coerce.number().int().min(0, "Position must be 0 or greater").max(100000),
    dependsOnIds: z.array(z.string()),
    toolBindings: z.array(z.string()),
  });

type FormValues = z.infer<typeof schema>;

/** Form page that adds a new task template to the workflow in the URL. */
export default function NewWorkflowTaskTemplatePage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [apiError, setApiError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<WorkflowTaskTemplate[]>([]);
  const [toolOptions, setToolOptions] = useState<McpToolOption[]>([]);

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
      position: 0,
      dependsOnIds: [] as string[],
      toolBindings: [] as string[],
    },
  });

  useEffect(() => {
    listWorkflowTaskTemplates(workflowId, { limit: 100 })
      .then(setCandidates)
      .catch(() => {
        // Candidate list is non-essential; the picker simply renders empty.
      });
  }, [workflowId]);

  useEffect(() => {
    loadMcpToolOptions()
      .then((catalog) => setToolOptions(catalog.options))
      .catch(() => {
        // Tool catalog is non-essential; the picker simply renders empty.
      });
  }, []);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await createWorkflowTaskTemplate({
          workflowId,
          title: values.title,
          description: values.description || null,
          position: values.position,
          dependsOnIds: values.dependsOnIds,
          toolBindings: values.toolBindings.map(valueToBinding),
        });
        dispatch(showToast({ message: "Template created" }));
        router.push(`/admin/workflows/${workflowId}/task-templates`);
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create template");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflows", href: "/admin/workflows" },
          { label: "Task Templates", href: `/admin/workflows/${workflowId}/task-templates` },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Task Template" icon={ListTree} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="title" label="Title" required error={errors.title?.message}>
            <Input id="title" placeholder="Short, actionable title" {...register("title")} />
          </FormField>

          <FormField htmlFor="description" label="Description">
            <Textarea
              id="description"
              rows={4}
              placeholder="Longer-form details (optional)"
              {...register("description")}
            />
          </FormField>

          <FormField htmlFor="position" label="Position" required error={errors.position?.message}>
            <Input id="position" type="number" min={0} step={1} {...register("position")} />
          </FormField>

          <FormField htmlFor="dependsOnIds" label="Depends on">
            <Controller
              control={control}
              name="dependsOnIds"
              render={({ field }) => (
                <CheckboxGroup
                  name="dependsOnIds"
                  options={candidates.map((t) => ({ value: t.id, label: t.title }))}
                  value={field.value}
                  onChange={field.onChange}
                  emptyMessage="No other templates in this workflow yet."
                />
              )}
            />
          </FormField>

          <FormField htmlFor="toolBindings" label="MCP Tools">
            <Controller
              control={control}
              name="toolBindings"
              render={({ field }) => (
                <CheckboxGroup
                  name="toolBindings"
                  options={toolOptions}
                  value={field.value}
                  onChange={field.onChange}
                  emptyMessage="No MCP tools available. Register MCP servers first."
                />
              )}
            />
          </FormField>

          <ErrorBanner error={apiError} />

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
              onClick={() => router.push(`/admin/workflows/${workflowId}/task-templates`)}
            >
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
