/** @module AgentSkillDetailPage — Admin edit/view form for an existing agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zAgentSkillCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { deleteAgentSkill, getAgentSkill, updateAgentSkill } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

const schema = zAgentSkillCreate;

type FormValues = z.infer<typeof schema>;

export default function EditAgentSkillPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", repoUrl: "", repoPath: "", description: "" },
  });

  useEffect(() => {
    getAgentSkill(skillId)
      .then((skill) => {
        reset({
          name: skill.name,
          repoUrl: skill.repoUrl,
          repoPath: skill.repoPath,
          description: skill.description ?? "",
        });
        setAudit({
          createdBy: skill.createdBy,
          updatedBy: skill.updatedBy,
          createdAt: skill.createdAt,
          updatedAt: skill.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load agent skill");
      })
      .finally(() => setLoading(false));
  }, [skillId, reset]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await updateAgentSkill(skillId, {
          name: values.name,
          repoUrl: values.repoUrl,
          repoPath: values.repoPath,
          description: values.description || null,
        });
        dispatch(showToast({ message: "Agent skill updated" }));
        router.push("/admin/agent-skills");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update agent skill");
    }
  }

  function handleDelete() {
    setConfirmOpen(true);
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteAgentSkill(skillId);
      router.push("/admin/agent-skills");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete agent skill");
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
          Edit Agent Skill
        </h1>
        <FormSkeleton fields={4} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        Edit Agent Skill
      </h1>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
      >
        <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
          <Input id="name" {...register("name")} />
        </FormField>

        <FormField htmlFor="repoUrl" label="Repo URL" required error={errors.repoUrl?.message}>
          <Input id="repoUrl" {...register("repoUrl")} />
        </FormField>

        <FormField htmlFor="repoPath" label="Repo Path">
          <Input id="repoPath" {...register("repoPath")} />
        </FormField>

        <FormField htmlFor="description" label="Description">
          <Textarea id="description" rows={4} {...register("description")} />
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
          <Button type="button" variant="ghost" onClick={() => router.push("/admin/agent-skills")}>
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
        title="Delete Agent Skill"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
