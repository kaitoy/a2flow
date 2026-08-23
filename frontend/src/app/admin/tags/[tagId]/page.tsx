/** @module TagDetailPage — Admin detail page for an existing tag. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Tags } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { TagColorField } from "@/components/admin/tag-color-field";
import {
  emptyTagFormValues,
  TagFields,
  type TagFormValues,
  tagFormSchema,
  toTagUpdateBody,
} from "@/components/admin/tag-fields";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteTag,
  getTag,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
  type TagColor,
  updateTag,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { DEFAULT_TAG_COLOR, resolveTagColor } from "@/lib/tag-palette";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Detail page of a tag: its name and its palette slot.
 *
 * Renaming is safe at any time — records reference a tag by id, so every record
 * carrying it picks up the new name with nothing to re-sync. Deleting, by
 * contrast, detaches it everywhere, which the confirmation says out loud.
 *
 * A viewer holding neither `admin` nor `developer` gets a read-only rendering —
 * reads are open to every authenticated user, but every tag write needs one of
 * those roles — so the fields show as plain values and Save/Delete are hidden
 * rather than left to fail with a 403 on click.
 */
export default function TagDetailPage() {
  const { tagId } = useParams<{ tagId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.ADMIN, Role.DEVELOPER);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // The persisted name, which titles the page. Kept out of the form so the
  // heading names the saved record rather than following every keystroke.
  const [name, setName] = useState("");
  const [color, setColor] = useState<TagColor>(DEFAULT_TAG_COLOR);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    watch,
    getValues,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(tagFormSchema),
    mode: "onBlur",
    defaultValues: emptyTagFormValues(),
  });

  useEffect(() => {
    getTag(tagId, SUPPRESS_FORBIDDEN_TOAST)
      .then((tag) => {
        setName(tag.name);
        setColor(resolveTagColor(tag.color));
        reset({ name: tag.name, description: tag.description ?? "" });
        setAudit({
          createdBy: tag.createdBy,
          updatedBy: tag.updatedBy,
          createdAt: tag.createdAt,
          updatedAt: tag.updatedAt,
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
  }, [tagId, reset]);

  async function onSubmit(values: TagFormValues) {
    try {
      await save.run(async () => {
        await updateTag(tagId, { ...toTagUpdateBody(values), color });
        dispatch(showToast({ message: "Tag updated" }));
        router.push("/admin/tags");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteTag(tagId);
      router.push("/admin/tags");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Tags", href: "/admin/tags" },
    // The tag itself is the current page; an ellipsis stands in until its name
    // has loaded.
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
        <FormLayout header={<AdminPageHeader icon={Tags} />}>
          <FormSkeleton fields={2} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={name} icon={Tags} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          {canEdit ? (
            <TagFields register={register} errors={errors} />
          ) : (
            <TagFields readOnly values={getValues()} />
          )}

          <TagColorField
            value={color}
            onChange={setColor}
            previewLabel={canEdit ? watch("name") : name}
            readOnly={!canEdit}
          />

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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/tags")}>
              {canEdit ? "Cancel" : "Back"}
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
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete Tag"
        description={`Delete "${name}"? It is removed from every record currently carrying it.`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
