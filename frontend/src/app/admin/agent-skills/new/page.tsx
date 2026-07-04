/** @module NewAgentSkillPage — Admin form for creating a new agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Wand2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zAgentSkillCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createAgentSkill } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

const schema = zAgentSkillCreate;

type FormValues = z.infer<typeof schema>;

export default function NewAgentSkillPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [apiError, setApiError] = useState<string | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", repoUrl: "", repoPath: "", description: "" },
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await createAgentSkill({
          name: values.name,
          repoUrl: values.repoUrl,
          repoPath: values.repoPath || undefined,
          description: values.description || null,
        });
        dispatch(showToast({ message: "Agent skill created" }));
        router.push("/admin/agent-skills");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create agent skill");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Agent Skills", href: "/admin/agent-skills" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Agent Skill" icon={Wand2} />

      <FormColumn>
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
