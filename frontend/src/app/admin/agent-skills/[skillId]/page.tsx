/** @module AgentSkillDetailPage — Admin edit/view form for an existing agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Wand2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zAgentSkillCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { deleteAgentSkill, getAgentSkill, updateAgentSkill } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// The generated auth fields are nullish with min-length 1, so a blank input
// would fail validation; the form allows the empty string ("no auth") and
// maps it to null on submit, clearing the field server-side.
const schema = zAgentSkillCreate.omit({ repoAuthSecret: true, repoAuthUsername: true }).extend({
  repoAuthSecret: z.literal("").or(zAgentSkillCreate.shape.repoAuthSecret.unwrap().unwrap()),
  repoAuthUsername: z.literal("").or(zAgentSkillCreate.shape.repoAuthUsername.unwrap().unwrap()),
});

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
    defaultValues: {
      name: "",
      repoUrl: "",
      repoPath: "",
      description: "",
      repoAuthSecret: "",
      repoAuthUsername: "",
    },
  });

  useEffect(() => {
    getAgentSkill(skillId)
      .then((skill) => {
        reset({
          name: skill.name,
          repoUrl: skill.repoUrl,
          repoPath: skill.repoPath,
          description: skill.description ?? "",
          repoAuthSecret: skill.repoAuthSecret ?? "",
          repoAuthUsername: skill.repoAuthUsername ?? "",
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
          repoAuthSecret: values.repoAuthSecret || null,
          repoAuthUsername: values.repoAuthUsername || null,
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

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Agent Skills", href: "/admin/agent-skills" },
    { label: "Edit" },
  ];

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AdminPageHeader title="Edit Agent Skill" icon={Wand2} />
        <FormColumn>
          <FormSkeleton fields={4} />
        </FormColumn>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="Edit Agent Skill" icon={Wand2} />

      <FormColumn>
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

          <FormField
            htmlFor="repoAuthSecret"
            label="Auth Secret"
            error={errors.repoAuthSecret?.message}
          >
            <Input
              id="repoAuthSecret"
              placeholder="Secret name for private repos (optional)"
              {...register("repoAuthSecret")}
            />
            <p className="mt-1 text-xs text-on-surface-variant">
              Name of a registered Secret used as the clone token for a private repository.
            </p>
          </FormField>

          <FormField
            htmlFor="repoAuthUsername"
            label="Auth Username"
            error={errors.repoAuthUsername?.message}
          >
            <Input
              id="repoAuthUsername"
              placeholder="x-access-token (default)"
              {...register("repoAuthUsername")}
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
            <Button type="button" variant="danger" onClick={handleDelete} className="ml-auto">
              Delete
            </Button>
          </div>
        </form>
        {audit && (
          <div className="mt-4">
            <AuditMeta {...audit} />
          </div>
        )}
      </FormColumn>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Agent Skill"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
