/** @module NewWorkflowTaskPage — Admin form for creating a new WorkflowTask under a session. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { zWorkflowTaskCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createWorkflowTask, listWorkflowTasks, type WorkflowTask } from "@/lib/api";
import { loadMcpToolOptions, type McpToolOption, valueToBinding } from "@/lib/mcp-tool-options";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the title/description/status/position constraints.
// The parent session id comes from the URL, and the form edits dependencies and
// tool bindings as plain string arrays (encoded values), so omit those and
// re-add them in the form's shape. Position is coerced from the number input.
const schema = zWorkflowTaskCreate
  .omit({
    workflowSessionId: true,
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

/** Form page that creates a new WorkflowTask belonging to the session in the URL. */
export default function NewWorkflowTaskPage() {
  const { wsId } = useParams<{ wsId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [apiError, setApiError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<WorkflowTask[]>([]);
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
      status: "pending" as const,
      position: 0,
      dependsOnIds: [] as string[],
      toolBindings: [] as string[],
    },
  });

  useEffect(() => {
    listWorkflowTasks(wsId, { limit: 100 })
      .then(setCandidates)
      .catch(() => {
        // Candidate list is non-essential; the picker simply renders empty.
      });
  }, [wsId]);

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
        await createWorkflowTask({
          workflowSessionId: wsId,
          title: values.title,
          description: values.description || null,
          status: values.status,
          position: values.position,
          dependsOnIds: values.dependsOnIds,
          toolBindings: values.toolBindings.map(valueToBinding),
        });
        dispatch(showToast({ message: "Task created" }));
        router.push(`/admin/workflow-sessions/${wsId}/workflow-tasks`);
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create task");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflow Sessions", href: "/admin/workflow-sessions" },
          { label: "Workflow Tasks", href: `/admin/workflow-sessions/${wsId}/workflow-tasks` },
          { label: "New" },
        ]}
      />
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        New Workflow Task
      </h1>

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

          <FormField htmlFor="status" label="Status" required error={errors.status?.message}>
            <Select id="status" {...register("status")}>
              <option value="pending">pending</option>
              <option value="in_progress">in progress</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="skipped">skipped</option>
            </Select>
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
                  emptyMessage="No other tasks in this session yet."
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
              onClick={() => router.push(`/admin/workflow-sessions/${wsId}/workflow-tasks`)}
            >
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
