"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createAgentSkill } from "@/lib/api";

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  repoUrl: z.string().url("Must be a valid URL").min(1, "Repo URL is required"),
  repoPath: z.string(),
  description: z.string(),
});

type FormValues = z.infer<typeof schema>;

export default function NewAgentSkillPage() {
  const router = useRouter();
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", repoUrl: "", repoPath: "", description: "" },
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await createAgentSkill({
        name: values.name,
        repoUrl: values.repoUrl,
        repoPath: values.repoPath || undefined,
        description: values.description || null,
      });
      router.push("/admin/agent-skills");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create agent skill");
    }
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        New Agent Skill
      </h1>

      <form
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
      >
        <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
          <Input id="name" placeholder="e.g. code-review" {...register("name")} />
        </FormField>

        <FormField htmlFor="repoUrl" label="Repo URL" required error={errors.repoUrl?.message}>
          <Input
            id="repoUrl"
            placeholder="https://github.com/owner/repo"
            {...register("repoUrl")}
          />
        </FormField>

        <FormField htmlFor="repoPath" label="Repo Path">
          <Input
            id="repoPath"
            placeholder="path/within/repo (optional)"
            {...register("repoPath")}
          />
        </FormField>

        <FormField htmlFor="description" label="Description">
          <Textarea
            id="description"
            rows={4}
            placeholder="What this skill does (optional)"
            {...register("description")}
          />
        </FormField>

        <ErrorBanner error={apiError} />

        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => router.push("/admin/agent-skills")}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}
