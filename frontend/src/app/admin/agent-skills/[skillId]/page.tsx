"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { deleteAgentSkill, getAgentSkill, updateAgentSkill } from "@/lib/api";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  repoUrl: z.string().url("Must be a valid URL").min(1, "Repo URL is required"),
  repoPath: z.string(),
  description: z.string(),
});

type FormValues = z.infer<typeof schema>;

export default function EditAgentSkillPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    getValues,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
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
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load agent skill");
      })
      .finally(() => setLoading(false));
  }, [skillId, reset]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await updateAgentSkill(skillId, {
        name: values.name,
        repoUrl: values.repoUrl,
        repoPath: values.repoPath,
        description: values.description || null,
      });
      router.push("/admin/agent-skills");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update agent skill");
    }
  }

  async function handleDelete() {
    if (!window.confirm(`Delete "${getValues("name")}"?`)) return;
    try {
      await deleteAgentSkill(skillId);
      router.push("/admin/agent-skills");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete agent skill");
    }
  }

  if (loading) {
    return <div className="p-8 text-on-surface-variant">Loading…</div>;
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
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
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
    </div>
  );
}
