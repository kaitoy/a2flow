/** @module GenerateWorkflowDialog — modal that starts workflow generation from an agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { animated, useTransition } from "@react-spring/web";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zGenerateWorkflowRequest } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { generateWorkflow } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";
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
 * name (prefilled with `defaultName`) plus the prompt the background planning
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
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

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

  useDialogA11y({ open, onClose, panelId: "generate-workflow-dialog", closeOnOutsideClick: false });

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

  // Guard against SSR — createPortal needs document.body.
  if (typeof document === "undefined") return null;

  return createPortal(
    transitions(
      (style, item) =>
        item && (
          <div className="fixed inset-0 z-50">
            <animated.button
              type="button"
              style={{ opacity: style.opacity }}
              className="absolute inset-0 h-full w-full cursor-default border-0 bg-black/25 backdrop-blur-[2px]"
              onClick={onClose}
              // Stop the backdrop itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              aria-label="Close workflow generation"
              tabIndex={-1}
            />
            <div className="relative flex min-h-full items-center justify-center p-4 pointer-events-none">
              <animated.div
                id="generate-workflow-dialog"
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby="generate-workflow-title"
                style={{
                  opacity: style.opacity,
                  transform: style.scale.to((s) => `scale(${s})`),
                }}
                className="w-full max-w-lg rounded-2xl glass-panel-overlay p-6 pointer-events-auto"
              >
                <h2
                  id="generate-workflow-title"
                  className="mb-1 font-display text-lg font-semibold tracking-tight text-on-surface"
                >
                  Generate Workflow
                </h2>
                <p className="mb-4 text-sm text-on-surface-variant">
                  A planning agent follows this skill to break the prompt into the workflow's task
                  list. The draft is registered right away and generation continues in the
                  background.
                </p>

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
                      placeholder="Describe the work; the planning agent breaks it into the workflow's task list"
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
              </animated.div>
            </div>
          </div>
        )
    ),
    document.body
  );
}
