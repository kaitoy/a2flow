/** @module EditWorkflowTaskTemplatePage — Admin form to edit or delete a task template. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ListTree } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zWorkflowTaskTemplateCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteWorkflowTaskTemplate,
  getWorkflowTaskTemplate,
  listWorkflowTaskTemplates,
  type ToolBinding,
  updateWorkflowTaskTemplate,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import {
  bindingToValue,
  loadMcpToolOptions,
  type McpToolCatalog,
  mergeBindingOptions,
  valueToBinding,
} from "@/lib/mcp-tool-options";
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

/** Form page that loads, updates, and deletes a single task template. */
export default function EditWorkflowTaskTemplatePage() {
  const { workflowId, templateId } = useParams<{ workflowId: string; templateId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [candidates, setCandidates] = useState<WorkflowTaskTemplate[]>([]);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [templateBindings, setTemplateBindings] = useState<ToolBinding[]>([]);
  const [toolCatalog, setToolCatalog] = useState<McpToolCatalog>({
    options: [],
    serverNames: new Map(),
  });

  const toolOptions = useMemo(
    () => mergeBindingOptions(toolCatalog.options, templateBindings, toolCatalog.serverNames),
    [toolCatalog, templateBindings]
  );

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    control,
    getValues,
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
    getWorkflowTaskTemplate(templateId)
      .then((template) => {
        reset({
          title: template.title,
          description: template.description ?? "",
          position: template.position ?? 0,
          dependsOnIds: template.dependsOnIds ?? [],
          toolBindings: (template.toolBindings ?? []).map(bindingToValue),
        });
        setTemplateBindings(template.toolBindings ?? []);
        setAudit({
          createdBy: template.createdBy,
          updatedBy: template.updatedBy,
          createdAt: template.createdAt,
          updatedAt: template.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load template");
      })
      .finally(() => setLoading(false));
  }, [templateId, reset]);

  useEffect(() => {
    listWorkflowTaskTemplates(workflowId, { limit: 100 })
      .then(setCandidates)
      .catch(() => {
        // Candidate list is non-essential; the picker simply renders empty.
      });
  }, [workflowId]);

  useEffect(() => {
    loadMcpToolOptions()
      .then(setToolCatalog)
      .catch(() => {
        // Tool catalog is non-essential; already-bound tools still render.
      });
  }, []);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await updateWorkflowTaskTemplate(templateId, {
          title: values.title,
          description: values.description || null,
          position: values.position,
          dependsOnIds: values.dependsOnIds,
          toolBindings: values.toolBindings.map(valueToBinding),
        });
        dispatch(showToast({ message: "Template updated" }));
        router.push(`/admin/workflows/${workflowId}/task-templates`);
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update template");
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteWorkflowTaskTemplate(templateId);
      router.push(`/admin/workflows/${workflowId}/task-templates`);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete template");
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Workflows", href: "/admin/workflows" },
    { label: "Task Templates", href: `/admin/workflows/${workflowId}/task-templates` },
    { label: "Edit" },
  ];

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AdminPageHeader title="Edit Task Template" icon={ListTree} />
        <FormColumn>
          <FormSkeleton fields={5} />
        </FormColumn>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="Edit Task Template" icon={ListTree} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <div className="text-xs text-on-surface-variant">
            Workflow ID: <span className="font-mono">{workflowId}</span>
          </div>

          <FormField htmlFor="title" label="Title" required error={errors.title?.message}>
            <Input id="title" {...register("title")} />
          </FormField>

          <FormField htmlFor="description" label="Description">
            <Textarea id="description" rows={4} {...register("description")} />
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
                  options={candidates
                    .filter((t) => t.id !== templateId)
                    .map((t) => ({ value: t.id, label: t.title }))}
                  value={field.value}
                  onChange={field.onChange}
                  emptyMessage="No other templates in this workflow to depend on."
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
            <Button
              type="button"
              variant="danger"
              onClick={() => setConfirmOpen(true)}
              className="ml-auto"
            >
              Delete
            </Button>
          </div>
        </form>
        {audit && (
          <div className="mt-4">
            <AuditMeta {...audit} />
          </div>
        )}
      </FormColumn>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Task Template"
        description={`Delete "${getValues("title")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
