/** @module AgentSkillDetailPage — Admin detail page for a registered agent skill. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { RefreshCw, Sparkles, Wand2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import {
  AgentSkillFields,
  type AgentSkillFormValues,
  agentSkillFormSchema,
  emptyAgentSkillFormValues,
  toAgentSkillUpdateBody,
} from "@/components/admin/agent-skill-fields";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { GenerateWorkflowDialog } from "@/components/admin/generate-workflow-dialog";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import { StatusCard } from "@/components/admin/status-card";
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { StatusDot } from "@/components/ui/status-dot";
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
  isForbiddenError,
  pullAgentSkill,
  type SkillSyncStatus,
  SUPPRESS_FORBIDDEN_TOAST,
  setAgentSkillTags,
  updateAgentSkill,
} from "@/lib/api";
import { sameIds } from "@/lib/ids";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** How often the page re-fetches the skill while its clone is still running. */
const POLL_INTERVAL_MS = 2000;

/** The server-managed clone/pull state of the skill on display. */
interface SyncState {
  status: SkillSyncStatus;
  error: string | null;
  commitSha: string | null;
}

/**
 * Detail page of a registered agent skill: its repository fields, the clone /
 * pull state of the skill store, and the entry point to generating a workflow
 * from it. The page is titled with the skill's own name.
 *
 * A viewer without the developer role gets a read-only rendering — reads are
 * open to every authenticated user, and a `requester` reaches this page from
 * the Agent Skill link on a workflow's detail page. The fields then show as
 * plain values (see {@link AgentSkillFields}'s `readOnly` mode) and every action
 * that would hit a developer-only endpoint — Generate Workflow, Pull, Save,
 * Delete — is hidden rather than left to fail with a 403 on click, the same
 * convention `WorkflowDetailPage` follows.
 */
export default function AgentSkillDetailPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [saveBeforeGenerateOpen, setSaveBeforeGenerateOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [sync, setSync] = useState<SyncState | null>(null);
  // The persisted name, which titles the page. Kept out of the form so the
  // heading names the saved record rather than following every keystroke.
  const [name, setName] = useState("");

  // Tags live outside the form state: the picker is a controlled
  // multi-select rather than a registered input. `savedTagIds` is what the
  // record carried when it loaded, so an untouched selection writes nothing.
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [savedTagIds, setSavedTagIds] = useState<string[]>([]);

  const save = useAsyncAction({ showDone: false });
  const pull = useAsyncAction({ showDone: false });
  const {
    register,
    control,
    handleSubmit,
    reset,
    getValues,
    formState: { errors, isDirty },
  } = useForm({
    resolver: zodResolver(agentSkillFormSchema),
    mode: "onBlur",
    defaultValues: emptyAgentSkillFormValues(),
  });

  const applySync = useCallback((skill: AgentSkill) => {
    setSync({
      status: (skill.syncStatus ?? "pending") as SkillSyncStatus,
      error: skill.syncError ?? null,
      commitSha: skill.commitSha ?? null,
    });
  }, []);

  useEffect(() => {
    getAgentSkill(skillId, SUPPRESS_FORBIDDEN_TOAST)
      .then((skill) => {
        setName(skill.name);
        setTagIds(skill.tagIds ?? []);
        setSavedTagIds(skill.tagIds ?? []);
        reset({
          name: skill.name,
          repoUrl: skill.repoUrl,
          repoPath: skill.repoPath,
          repoRef: skill.repoRef ?? "",
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
      .catch((err: unknown) => {
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
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

  /**
   * Persist the form and clear its dirty state. Throws when the request fails
   * so callers can skip whatever they meant to do next.
   */
  async function persist(values: AgentSkillFormValues) {
    await save.run(async () => {
      await updateAgentSkill(skillId, toAgentSkillUpdateBody(values));
      // Tags are a separate sub-resource, so they are only written when
      // the selection actually changed.
      if (!sameIds(tagIds, savedTagIds)) {
        await setAgentSkillTags(skillId, tagIds);
      }
      setName(values.name);
      dispatch(showToast({ message: "Agent skill updated" }));
      // Re-seed the form with what was just saved so `isDirty` goes back to
      // false — the generation flow reads it to decide whether to ask.
      reset(values);
    });
  }

  async function onSubmit(values: AgentSkillFormValues) {
    try {
      await persist(values);
      router.push("/admin/agent-skills");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  // Generating navigates away to the new workflow, so unsaved edits would be
  // lost. Offer to save them first rather than dropping them silently.
  function handleGenerateClick() {
    if (isDirty) {
      setSaveBeforeGenerateOpen(true);
      return;
    }
    setGenerateOpen(true);
  }

  function confirmSaveBeforeGenerate() {
    setSaveBeforeGenerateOpen(false);
    // Route through handleSubmit so the edits are validated before they are
    // saved; an invalid form surfaces its errors and the dialog stays shut.
    void handleSubmit(async (values) => {
      try {
        await persist(values);
        setGenerateOpen(true);
      } catch {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      }
    })();
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
    // The skill itself is the current page; an ellipsis stands in until its
    // name has loaded.
    { label: name || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={Wand2} />}>
          <FormSkeleton fields={4} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={
          <AdminPageHeader
            title={name}
            icon={Wand2}
            secondaryAction={
              canEdit ? (
                <HeaderIconButton
                  label="Generate Workflow"
                  onClick={handleGenerateClick}
                  // A skill can only back a design run once its clone has
                  // published a revision.
                  disabled={sync?.status !== "ready"}
                >
                  <Sparkles size={18} strokeWidth={1.8} aria-hidden="true" />
                </HeaderIconButton>
              ) : undefined
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        {sync && (
          <StatusCard
            ariaLabel="Repository sync"
            actions={
              canEdit ? (
                <ActionIconButton
                  icon={RefreshCw}
                  label="Pull"
                  onClick={handlePull}
                  disabled={pull.inFlight || sync.status === "pending"}
                  spinning={pull.inFlight || sync.status === "pending"}
                />
              ) : undefined
            }
            error={sync.error}
          >
            <StatusDot
              dotClass={SYNC_STATUS_DOT_CLASS[sync.status]}
              label={formatSyncStatusLabel(sync.status)}
            />
            <div className="flex items-center gap-2 text-sm text-on-surface-variant">
              <span>Revision</span>
              <span className="font-mono">{formatRevision(sync.commitSha)}</span>
            </div>
          </StatusCard>
        )}

        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          {canEdit ? (
            <AgentSkillFields register={register} control={control} errors={errors} />
          ) : (
            <AgentSkillFields readOnly values={getValues()} />
          )}

          <TagPicker value={tagIds} onChange={setTagIds} readOnly={!canEdit} />

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
              {canEdit ? "Cancel" : "Back"}
            </Button>
            {canEdit && (
              <Button type="button" variant="danger" onClick={handleDelete} className="ml-auto">
                Delete
              </Button>
            )}
          </div>
        </form>
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Agent Skill"
        description={`Delete "${getValues("name")}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
      <ConfirmDialog
        open={saveBeforeGenerateOpen}
        title="Save changes?"
        description="Generating opens the new workflow, leaving this page. Save your changes to this skill first?"
        confirmLabel="Save and continue"
        confirmVariant="primary"
        onConfirm={confirmSaveBeforeGenerate}
        onCancel={() => setSaveBeforeGenerateOpen(false)}
      />
      <GenerateWorkflowDialog
        open={generateOpen}
        skillId={skillId}
        defaultName={getValues("name")}
        onClose={() => setGenerateOpen(false)}
      />
    </AdminPageContainer>
  );
}
