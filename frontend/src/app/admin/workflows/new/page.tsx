/** @module NewWorkflowPage — Admin form for creating a new workflow. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ErrorBanner } from "@/components/admin/error-banner";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { zWorkflowCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { type AgentSkill, createWorkflow, listAgentSkills } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries name/prompt/description constraints; tighten the
// agentSkillId foreign key to a required selection for the form's dropdown.
const schema = zWorkflowCreate.extend({
  agentSkillId: z.string().min(1, "Agent skill is required"),
});

type FormValues = z.infer<typeof schema>;

export default function NewWorkflowPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [apiError, setApiError] = useState<string | null>(null);
  const [skills, setSkills] = useState<AgentSkill[]>([]);

  useEffect(() => {
    listAgentSkills({ limit: 1000 })
      .then(setSkills)
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load agent skills");
      });
  }, []);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", prompt: "", agentSkillId: "", description: "" },
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await createWorkflow({
          name: values.name,
          prompt: values.prompt,
          agentSkillId: values.agentSkillId,
          description: values.description || null,
        });
        dispatch(showToast({ message: "Workflow created" }));
        router.push("/admin/workflows");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create workflow");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Workflows", href: "/admin/workflows" },
          { label: "New" },
        ]}
      />
      <h1 className="mb-6 text-3xl font-semibold tracking-tight text-gradient-accent">
        New Workflow
      </h1>

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" placeholder="e.g. code-review-flow" {...register("name")} />
          </FormField>

          <FormField
            htmlFor="agentSkillId"
            label="Agent Skill"
            required
            error={errors.agentSkillId?.message}
          >
            <Select id="agentSkillId" {...register("agentSkillId")}>
              <option value="">— Select a skill —</option>
              {skills.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </FormField>

          <FormField htmlFor="prompt" label="Prompt" required error={errors.prompt?.message}>
            <Textarea
              id="prompt"
              rows={6}
              placeholder="Instructions for the agent (required)"
              {...register("prompt")}
            />
          </FormField>

          <FormField htmlFor="description" label="Description">
            <Textarea
              id="description"
              rows={3}
              placeholder="What this workflow does (optional)"
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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/workflows")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
