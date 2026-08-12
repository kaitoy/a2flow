/** @module GenerateWorkflowDialog — modal that starts workflow generation from an agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zGenerateWorkflowRequest } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { generateWorkflow } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Generated schema carries the name/prompt constraints as-is.
const schema = zGenerateWorkflowRequest;

type FormValues = z.infer<typeof schema>;

/** Props for {@link GenerateWorkflowDialog}. */
export interface GenerateWorkflowDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Identifier of the agent skill the workflow is generated from. */
  skillId: string;
  /** Initial value for the workflow name — normally the skill's own name. */
  defaultName: string;
  /** Called when the dialog requests to close (backdrop, Escape, or Cancel). */
  onClose: () => void;
}

/**
 * Modal dialog that starts "Generate workflow" for an agent skill: the workflow
 * name (prefilled with `defaultName`) plus the prompt the background design
 * run breaks into the workflow's task templates.
 *
 * On submit the draft workflow is registered immediately and the app navigates
 * to its detail page, which polls until generation settles — so the dialog
 * never has to report generation progress itself.
 */
export function GenerateWorkflowDialog({
  open,
  skillId,
  defaultName,
  onClose,
}: GenerateWorkflowDialogProps) {
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
    defaultValues: { name: defaultName, prompt: "" },
  });

  // Re-seed the form every time the dialog opens, so reopening it for another
  // skill (the list page reuses one instance) never shows the previous input.
  useEffect(() => {
    if (!open) return;
    reset({ name: defaultName, prompt: "" });
  }, [open, defaultName, reset]);

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
    <Dialog
      open={open}
      onClose={onClose}
      panelId="generate-workflow-dialog"
      title="Generate Workflow"
      description="A design agent follows this skill to break the prompt into the workflow's task list. The draft is registered right away and generation continues in the background."
      // Signature "live edge" while the design run is being handed to the agent.
      // Gated on the 200ms `pending` stage so a fast registration never flashes
      // the light.
      panelClassName={save.status === "pending" ? "live-edge" : undefined}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
        <FormField
          htmlFor="generate-workflow-name"
          label="Workflow Name"
          required
          error={errors.name?.message}
        >
          <Input
            id="generate-workflow-name"
            placeholder="Defaults to the skill name"
            {...register("name")}
          />
        </FormField>

        <FormField
          htmlFor="generate-workflow-prompt"
          label="Prompt"
          required
          error={errors.prompt?.message}
        >
          <Textarea
            id="generate-workflow-prompt"
            rows={6}
            placeholder="Describe the work; the design agent breaks it into the workflow's task list"
            {...register("prompt")}
          />
        </FormField>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={save.inFlight}
            status={save.status}
            pendingLabel="Generating…"
          >
            Generate
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
