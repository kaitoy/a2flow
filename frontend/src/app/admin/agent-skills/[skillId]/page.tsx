"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
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
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", repoUrl: "", repoPath: "", description: "" },
  });

  useEffect(() => {
    getAgentSkill(skillId)
      .then((skill) => {
        reset({
          name: skill.name,
          repoUrl: skill.repo_url,
          repoPath: skill.repo_path,
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
        repo_url: values.repoUrl,
        repo_path: values.repoPath,
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
    <div className="p-8">
      <h1 className="mb-6 text-2xl font-semibold text-on-surface">Edit Agent Skill</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="flex max-w-lg flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label
            htmlFor="name"
            className="text-xs font-bold uppercase tracking-[0.04em] text-on-surface-variant"
          >
            Name <span className="text-error">*</span>
          </label>
          <Input id="name" {...register("name")} />
          {errors.name && <p className="text-xs text-error">{errors.name.message}</p>}
        </div>

        <div className="flex flex-col gap-1">
          <label
            htmlFor="repoUrl"
            className="text-xs font-bold uppercase tracking-[0.04em] text-on-surface-variant"
          >
            Repo URL <span className="text-error">*</span>
          </label>
          <Input id="repoUrl" {...register("repoUrl")} />
          {errors.repoUrl && <p className="text-xs text-error">{errors.repoUrl.message}</p>}
        </div>

        <div className="flex flex-col gap-1">
          <label
            htmlFor="repoPath"
            className="text-xs font-bold uppercase tracking-[0.04em] text-on-surface-variant"
          >
            Repo Path
          </label>
          <Input id="repoPath" {...register("repoPath")} />
        </div>

        <div className="flex flex-col gap-1">
          <label
            htmlFor="description"
            className="text-xs font-bold uppercase tracking-[0.04em] text-on-surface-variant"
          >
            Description
          </label>
          <Textarea id="description" rows={4} {...register("description")} />
        </div>

        {apiError && (
          <div className="rounded bg-error-container p-3 text-sm text-on-error-container">
            {apiError}
          </div>
        )}

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
