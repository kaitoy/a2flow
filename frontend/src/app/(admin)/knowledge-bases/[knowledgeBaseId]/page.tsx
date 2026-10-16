/** @module KnowledgeBaseDetailPage — Admin detail page for one knowledge base. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BookOpen, Download } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { HeaderIconButton } from "@/components/admin/header-icon-button";
import {
  emptyKnowledgeBaseFormValues,
  KnowledgeBaseFields,
  type KnowledgeBaseFormValues,
  knowledgeBaseFormSchema,
  toKnowledgeBaseBody,
} from "@/components/admin/knowledge-base-fields";
import { KnowledgePagesPanel } from "@/components/admin/knowledge-pages-panel";
import { KnowledgeSourcesPanel } from "@/components/admin/knowledge-sources-panel";
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import {
  deleteKnowledgeBase,
  getKnowledgeBase,
  isForbiddenError,
  knowledgeBaseExportUrl,
  SUPPRESS_FORBIDDEN_TOAST,
  setKnowledgeBaseTags,
  updateKnowledgeBase,
} from "@/lib/api";
import { sameIds } from "@/lib/ids";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Detail page of one knowledge base: its name and description, the sources it
 * is written from, and the pages written so far. The page is titled with the
 * knowledge base's own name.
 *
 * A viewer without the developer role gets a read-only rendering, with no way
 * to add or remove sources; anyone who can open the page may read its pages and
 * download the bundle.
 */
export default function KnowledgeBaseDetailPage() {
  const { knowledgeBaseId } = useParams<{ knowledgeBaseId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const isAllTenantsView = useIsAllTenantsView();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // The persisted name, which titles the page.
  const [name, setName] = useState("");
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [savedTagIds, setSavedTagIds] = useState<string[]>([]);
  // Bumped when the sources panel reports that background work finished, so
  // the pages panel shows what that work wrote.
  const [pagesKey, setPagesKey] = useState(0);
  const refreshPages = useCallback(() => setPagesKey((k) => k + 1), []);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    formState: { errors },
  } = useForm<KnowledgeBaseFormValues>({
    resolver: zodResolver(knowledgeBaseFormSchema),
    mode: "onBlur",
    defaultValues: emptyKnowledgeBaseFormValues(),
  });

  useEffect(() => {
    getKnowledgeBase(knowledgeBaseId, SUPPRESS_FORBIDDEN_TOAST)
      .then((kb) => {
        setName(kb.name);
        reset({ name: kb.name, description: kb.description ?? "" });
        setTagIds(kb.tagIds ?? []);
        setSavedTagIds(kb.tagIds ?? []);
        setAudit({
          createdBy: kb.createdBy,
          updatedBy: kb.updatedBy,
          createdAt: kb.createdAt,
          updatedAt: kb.updatedAt,
          tenantId: isAllTenantsView ? kb.tenantId : undefined,
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
  }, [knowledgeBaseId, reset, isAllTenantsView]);

  async function onSubmit(values: KnowledgeBaseFormValues) {
    try {
      await save.run(async () => {
        await updateKnowledgeBase(knowledgeBaseId, toKnowledgeBaseBody(values));
        if (!sameIds(tagIds, savedTagIds)) {
          await setKnowledgeBaseTags(knowledgeBaseId, tagIds);
          setSavedTagIds(tagIds);
        }
        setName(values.name);
        reset(values);
        dispatch(showToast({ message: "Knowledge base updated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteKnowledgeBase(knowledgeBaseId);
      router.push("/knowledge-bases");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Home", href: "/" },
    { label: "Knowledge Bases", href: "/knowledge-bases" },
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
        <FormLayout header={<AdminPageHeader icon={BookOpen} />}>
          <FormSkeleton fields={2} />
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
            icon={BookOpen}
            secondaryAction={
              <HeaderIconButton
                label="Download bundle"
                // Served as an attachment, so the browser downloads it in place.
                onClick={() => window.location.assign(knowledgeBaseExportUrl(knowledgeBaseId))}
              >
                <Download size={18} strokeWidth={1.8} aria-hidden="true" />
              </HeaderIconButton>
            }
          />
        }
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          {canEdit ? (
            <KnowledgeBaseFields register={register} errors={errors} />
          ) : (
            <KnowledgeBaseFields readOnly values={getValues()} />
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
            <Button type="button" variant="ghost" onClick={() => router.push("/knowledge-bases")}>
              Back
            </Button>
            {canEdit && (
              <Button
                type="button"
                variant="danger"
                onClick={() => setConfirmOpen(true)}
                className="ml-auto"
              >
                Delete
              </Button>
            )}
          </div>
        </form>
        <KnowledgeSourcesPanel
          knowledgeBaseId={knowledgeBaseId}
          canEdit={canEdit}
          onSettled={refreshPages}
        />
        <KnowledgePagesPanel knowledgeBaseId={knowledgeBaseId} refreshKey={pagesKey} />
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Knowledge Base"
        description={`Delete "${name}" with all its sources and pages? Workflows linked to it lose access to it.`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
