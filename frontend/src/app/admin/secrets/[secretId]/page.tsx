/** @module EditSecretPage — Admin edit/view form for a registered secret. */
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
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { deleteSecret, getSecret, updateSecret } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/**
 * Editing allows blank entry values: the API never returns a stored value, so a
 * blank one is the sentinel that keeps it.
 */
const schema = buildSecretFormSchema(false);

export default function EditSecretPage() {
  const { secretId } = useParams<{ secretId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);

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
    getSecret(secretId)
      .then((secret) => {
        reset({
          name: secret.name,
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
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [secretId, reset]);

  async function onSubmit(values: SecretFormValues) {
    try {
      await save.run(async () => {
        await updateSecret(secretId, toSecretBody(values));
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
    { label: "Edit" },
  ];

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader title="Edit Secret" icon={KeyRound} />}>
          <FormSkeleton fields={3} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title="Edit Secret" icon={KeyRound} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <SecretFields register={register} control={control} errors={errors} type={type} />

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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/secrets")}>
              Cancel
            </Button>
            <Button type="button" variant="danger" onClick={handleDelete} className="ml-auto">
              Delete
            </Button>
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
