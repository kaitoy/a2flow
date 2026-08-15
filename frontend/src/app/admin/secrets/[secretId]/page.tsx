/** @module SecretDetailPage — Admin detail page for a registered secret. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import {
  buildSecretFormSchema,
  emptySecretFormValues,
  SecretFields,
  type SecretFormValues,
  toSecretBody,
} from "@/components/admin/secret-fields";
import { TagPicker } from "@/components/admin/tag-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  deleteSecret,
  getSecret,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
  setSecretTags,
  updateSecret,
} from "@/lib/api";
import { sameIds } from "@/lib/ids";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Editing allows blank entry values: the API never returns a stored value, so a
 * blank one is the sentinel that keeps it.
 */
const schema = buildSecretFormSchema(false);

/**
 * Detail page of a registered secret: its type and the entry keys it holds
 * (values are write-only). The page is titled with the secret's own name.
 *
 * A viewer with neither the admin nor developer role gets a read-only
 * rendering — reads are open to every authenticated user, but writes need one
 * of those two roles — so the fields show as plain values, with a `local`
 * secret's entries listed by key alone (see {@link SecretFields}'s `readOnly`
 * mode), and Save/Delete are hidden rather than left to fail with a 403 on
 * click.
 */
export default function SecretDetailPage() {
  const { secretId } = useParams<{ secretId: string }>();
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

  // Tags live outside the form state: the picker is a controlled
  // multi-select rather than a registered input. `savedTagIds` is what the
  // record carried when it loaded, so an untouched selection writes nothing.
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [savedTagIds, setSavedTagIds] = useState<string[]>([]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    control,
    watch,
    getValues,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: emptySecretFormValues(),
  });
  const type = watch("type");

  useEffect(() => {
    getSecret(secretId, SUPPRESS_FORBIDDEN_TOAST)
      .then((secret) => {
        setName(secret.name);
        setTagIds(secret.tagIds ?? []);
        setSavedTagIds(secret.tagIds ?? []);
        reset({
          name: secret.name,
          description: secret.description ?? "",
          type: secret.type,
          // Values are write-only, so each stored key comes back with a blank
          // value the user may either leave (keeping it) or overwrite.
          entries: (secret.keys ?? []).map((key) => ({ key, value: "" })),
          vaultMount: secret.vaultMount ?? "",
          vaultPath: secret.vaultPath ?? "",
        });
        setAudit({
          createdBy: secret.createdBy,
          updatedBy: secret.updatedBy,
          createdAt: secret.createdAt,
          updatedAt: secret.updatedAt,
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
  }, [secretId, reset]);

  async function onSubmit(values: SecretFormValues) {
    try {
      await save.run(async () => {
        await updateSecret(secretId, toSecretBody(values));
        // Tags are a separate sub-resource, so they are only written when
        // the selection actually changed.
        if (!sameIds(tagIds, savedTagIds)) {
          await setSecretTags(secretId, tagIds);
        }
        dispatch(showToast({ message: "Secret updated" }));
        router.push("/admin/secrets");
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
      await deleteSecret(secretId);
      router.push("/admin/secrets");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Secrets", href: "/admin/secrets" },
    // The secret itself is the current page; an ellipsis stands in until its
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
        <FormLayout header={<AdminPageHeader icon={KeyRound} />}>
          <FormSkeleton fields={3} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={name} icon={KeyRound} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          {canEdit ? (
            <SecretFields register={register} control={control} errors={errors} type={type} />
          ) : (
            <SecretFields readOnly values={getValues()} />
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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/secrets")}>
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
        title="Delete Secret"
        description={`Delete "${getValues("name")}"? Anything still referencing it will fail at its next use.`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
