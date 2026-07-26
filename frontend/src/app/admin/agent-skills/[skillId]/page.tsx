/** @module AgentSkillDetailPage — Admin edit/view form for an existing agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { RefreshCw, Wand2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zAgentSkillCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  formatRevision,
  formatSyncStatusLabel,
  SYNC_STATUS_DOT_CLASS,
} from "@/lib/agent-skill-sync-status";
import {
  type AgentSkill,
  deleteAgentSkill,
  getAgentSkill,
  pullAgentSkill,
  type SkillSyncStatus,
  updateAgentSkill,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// The generated auth fields are nullish with min-length 1, so a blank input
// would fail validation; the form allows the empty string ("no auth") and
// maps it to null on submit, clearing the field server-side.
const schema = zAgentSkillCreate.omit({ repoAuthPassword: true, repoAuthUsername: true }).extend({
  repoAuthPassword: z.literal("").or(zAgentSkillCreate.shape.repoAuthPassword.unwrap().unwrap()),
  repoAuthUsername: z.literal("").or(zAgentSkillCreate.shape.repoAuthUsername.unwrap().unwrap()),
});

type FormValues = z.infer<typeof schema>;

/** How often the page re-fetches the skill while its clone is still running. */
const POLL_INTERVAL_MS = 2000;

/** The server-managed clone/pull state of the skill being edited. */
interface SyncState {
  status: SkillSyncStatus;
  error: string | null;
  commitSha: string | null;
}

export default function EditAgentSkillPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [sync, setSync] = useState<SyncState | null>(null);

  const save = useAsyncAction({ showDone: false });
  const pull = useAsyncAction({ showDone: false });
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
      repoAuthPassword: "",
      repoAuthUsername: "",
    },
  });

  const applySync = useCallback((skill: AgentSkill) => {
    setSync({
      status: (skill.syncStatus ?? "pending") as SkillSyncStatus,
      error: skill.syncError ?? null,
      commitSha: skill.commitSha ?? null,
    });
  }, []);

  useEffect(() => {
    getAgentSkill(skillId)
      .then((skill) => {
        reset({
          name: skill.name,
          repoUrl: skill.repoUrl,
          repoPath: skill.repoPath,
          description: skill.description ?? "",
          repoAuthPassword: skill.repoAuthPassword ?? "",
          repoAuthUsername: skill.repoAuthUsername ?? "",
        });
        applySync(skill);
        setAudit({
          createdBy: skill.createdBy,
          updatedBy: skill.updatedBy,
          createdAt: skill.createdAt,
          updatedAt: skill.updatedAt,
        });
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [skillId, reset, applySync]);

  // The clone runs in the background on the server and nothing pushes its
  // result here, so poll until it lands on ready or failed.
  useEffect(() => {
    if (sync?.status !== "pending") return;
    const timer = setInterval(() => {
      getAgentSkill(skillId)
        .then(applySync)
        .catch(() => {
          // Non-fatal: the next tick retries, and the form itself still works.
        });
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [sync?.status, skillId, applySync]);

  async function handlePull() {
    try {
      await pull.run(async () => {
        applySync(await pullAgentSkill(skillId));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await updateAgentSkill(skillId, {
          name: values.name,
          repoUrl: values.repoUrl,
          repoPath: values.repoPath,
          description: values.description || null,
          repoAuthPassword: values.repoAuthPassword || null,
          repoAuthUsername: values.repoAuthUsername || null,
        });
        dispatch(showToast({ message: "Agent skill updated" }));
        router.push("/admin/agent-skills");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
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
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
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
        {sync && (
          <section
            aria-label="Repository sync"
            className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 rounded-2xl glass-panel p-4"
          >
            <div className="flex items-center gap-2">
              <span
                className={`inline-block size-2 rounded-full ${SYNC_STATUS_DOT_CLASS[sync.status]}`}
                aria-hidden
              />
              <span className="capitalize">{formatSyncStatusLabel(sync.status)}</span>
            </div>
            <div className="flex items-center gap-2 text-sm text-on-surface-variant">
              <span>Revision</span>
              <span className="font-mono">{formatRevision(sync.commitSha)}</span>
            </div>
            {canEdit && (
              <div className="ml-auto">
                <ActionIconButton
                  icon={RefreshCw}
                  label="Pull"
                  onClick={handlePull}
                  disabled={pull.inFlight || sync.status === "pending"}
                  spinning={pull.inFlight || sync.status === "pending"}
                />
              </div>
            )}
            {sync.error && (
              <p className="w-full break-words font-mono text-error text-xs">{sync.error}</p>
            )}
          </section>
        )}

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
            htmlFor="repoAuthUsername"
            label="Auth Username"
            error={errors.repoAuthUsername?.message}
          >
            <Input
              id="repoAuthUsername"
              placeholder="e.g. octocat (optional)"
              {...register("repoAuthUsername")}
            />
          </FormField>

          <FormField
            htmlFor="repoAuthPassword"
            label="Auth Password"
            error={errors.repoAuthPassword?.message}
          >
            <Input
              id="repoAuthPassword"
              placeholder="name/key for private repos (optional)"
              {...register("repoAuthPassword")}
            />
            <p className="mt-1 text-xs text-on-surface-variant">
              One entry of a registered Secret, written as name/key, used as the clone token for a
              private repository.
            </p>
          </FormField>

          <div className="flex gap-2">
            {canEdit && (
              <Button
                type="submit"
                variant="primary"
                disabled={save.inFlight}
                status={save.status}
                pendingLabel="Saving…"
              >
                Save
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push("/admin/agent-skills")}
            >
              Cancel
            </Button>
            {canEdit && (
              <Button type="button" variant="danger" onClick={handleDelete} className="ml-auto">
                Delete
              </Button>
            )}
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
