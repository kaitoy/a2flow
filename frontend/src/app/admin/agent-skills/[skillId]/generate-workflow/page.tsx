/** @module GenerateWorkflowPage — Admin form that generates a draft workflow from a skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Sparkles } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zGenerateWorkflowRequest } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { generateWorkflow, getAgentSkill } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the name/prompt constraints as-is.
const schema = zGenerateWorkflowRequest;

type FormValues = z.infer<typeof schema>;

/**
 * Form page that starts "Generate workflow" for the skill in the URL: the
 * workflow name (prefilled with the skill name) plus the prompt the background
 * planning run breaks into the workflow's task templates. On submit the draft
 * workflow is registered immediately and the page navigates to its detail
 * view, which polls until generation settles.
 */
export default function GenerateWorkflowPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", prompt: "" },
  });

  // Prefill the workflow name with the skill name (still editable).
  useEffect(() => {
    getAgentSkill(skillId)
      .then((skill) => reset({ name: skill.name, prompt: "" }))
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      });
  }, [skillId, reset]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        const workflow = await generateWorkflow(skillId, {
          name: values.name,
          prompt: values.prompt,
        });
        dispatch(showToast({ message: "Workflow generation started" }));
        router.push(`/admin/workflows/${workflow.id}`);
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Agent Skills", href: "/admin/agent-skills" },
          { label: "Generate Workflow" },
        ]}
      />
      <AdminPageHeader title="Generate Workflow" icon={Sparkles} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Workflow Name" required error={errors.name?.message}>
            <Input id="name" placeholder="Defaults to the skill name" {...register("name")} />
          </FormField>

          <FormField htmlFor="prompt" label="Prompt" required error={errors.prompt?.message}>
            <Textarea
              id="prompt"
              rows={6}
              placeholder="Describe the work; the planning agent breaks it into the workflow's task list"
              {...register("prompt")}
            />
          </FormField>

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel="Generating…"
            >
              Generate
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
