/** @module EditWorkflowTaskPage — Admin form to edit or delete an existing WorkflowTask. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  deleteWorkflowTask,
  getWorkflowTask,
  listWorkflowTasks,
  updateWorkflowTask,
  type WorkflowTask,
} from "@/lib/api";

const schema = z.object({
  title: z.string().min(1, "Title is required"),
  description: z.string(),
  status: z.enum(["pending", "in_progress", "completed", "failed", "skipped"]),
  position: z.coerce.number().int().min(0, "Position must be 0 or greater"),
  dependsOnIds: z.array(z.string()),
});

type FormValues = z.infer<typeof schema>;

/** Form page that loads, updates, and deletes a single WorkflowTask. */
export default function EditWorkflowTaskPage() {
  const { wsId, taskId } = useParams<{ wsId: string; taskId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [candidates, setCandidates] = useState<WorkflowTask[]>([]);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    control,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      title: "",
      description: "",
      status: "pending" as const,
      position: 0,
      dependsOnIds: [] as string[],
    },
  });

  useEffect(() => {
    getWorkflowTask(taskId)
      .then((task) => {
        reset({
          title: task.title,
          description: task.description ?? "",
          status: task.status ?? "pending",
          position: task.position ?? 0,
          dependsOnIds: task.dependsOnIds ?? [],
        });
        setAudit({
          createdBy: task.createdBy,
          updatedBy: task.updatedBy,
          createdAt: task.createdAt,
          updatedAt: task.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load task");
      })
      .finally(() => setLoading(false));
  }, [taskId, reset]);

  useEffect(() => {
    listWorkflowTasks(wsId, 100)
      .then(setCandidates)
      .catch(() => {
        // Candidate list is non-essential; the picker simply renders empty.
      });
  }, [wsId]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await updateWorkflowTask(taskId, {
        title: values.title,
        description: values.description || null,
        status: values.status,
        position: values.position,
        dependsOnIds: values.dependsOnIds,
      });
      router.push(`/admin/workflow-sessions/${wsId}/workflow-tasks`);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update task");
    }
  }

  function handleDelete() {
    setConfirmOpen(true);
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteWorkflowTask(taskId);
      router.push(`/admin/workflow-sessions/${wsId}/workflow-tasks`);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete task");
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
          Edit Workflow Task
        </h1>
        <FormSkeleton fields={6} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        Edit Workflow Task
      </h1>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
      >
        <div className="text-xs text-on-surface-variant">
          Session ID: <span className="font-mono">{wsId}</span>
        </div>

        <FormField htmlFor="title" label="Title" required error={errors.title?.message}>
          <Input id="title" {...register("title")} />
        </FormField>

        <FormField htmlFor="description" label="Description">
          <Textarea id="description" rows={4} {...register("description")} />
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
                options={candidates
                  .filter((t) => t.id !== taskId)
                  .map((t) => ({ value: t.id, label: t.title }))}
                value={field.value}
                onChange={field.onChange}
                emptyMessage="No other tasks in this session to depend on."
              />
            )}
          />
        </FormField>

        <ErrorBanner error={apiError} />

        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.push(`/admin/workflow-sessions/${wsId}/workflow-tasks`)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={handleDelete}
            className="ml-auto text-error"
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
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Workflow Task"
        description={`Delete "${getValues("title")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
