/** @module EditSecretPage — Admin edit/view form for a registered secret. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
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
import { SegmentedControl } from "@/components/ui/segmented-control";
import { zSecretCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { deleteSecret, getSecret, type SecretUpdate, updateSecret } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Like the create form, per-type fields are plain strings validated here. The
// value is left blank to keep the stored one (the API never returns it), so
// only the Vault reference fields are client-required; the backend rejects a
// type switch to local without a value.
const schema = z
  .object({
    name: zSecretCreate.shape.name,
    type: zSecretCreate.shape.type,
    value: z.string().max(8192),
    vaultMount: z.string().max(256),
    vaultPath: z.string().max(1024),
    vaultKey: z.string().max(256),
  })
  .superRefine((v, ctx) => {
    if (v.type === "vault") {
      for (const field of ["vaultMount", "vaultPath", "vaultKey"] as const) {
        if (v[field] === "") {
          ctx.addIssue({ code: "custom", path: [field], message: "Required for a Vault secret" });
        }
      }
    }
  });

type FormValues = z.infer<typeof schema>;

export default function EditSecretPage() {
  const { secretId } = useParams<{ secretId: string }>();
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
    control,
    watch,
    getValues,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      name: "",
      type: "local" as const,
      value: "",
      vaultMount: "",
      vaultPath: "",
      vaultKey: "",
    },
  });
  const type = watch("type");

  useEffect(() => {
    getSecret(secretId)
      .then((secret) => {
        reset({
          name: secret.name,
          type: secret.type,
          value: "",
          vaultMount: secret.vaultMount ?? "",
          vaultPath: secret.vaultPath ?? "",
          vaultKey: secret.vaultKey ?? "",
        });
        setAudit({
          createdBy: secret.createdBy,
          updatedBy: secret.updatedBy,
          createdAt: secret.createdAt,
          updatedAt: secret.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load secret");
      })
      .finally(() => setLoading(false));
  }, [secretId, reset]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    const body: SecretUpdate =
      values.type === "local"
        ? {
            name: values.name,
            type: "local",
            // A blank value keeps the stored one.
            ...(values.value === "" ? {} : { value: values.value }),
          }
        : {
            name: values.name,
            type: "vault",
            vaultMount: values.vaultMount,
            vaultPath: values.vaultPath,
            vaultKey: values.vaultKey,
          };
    try {
      await save.run(async () => {
        await updateSecret(secretId, body);
        dispatch(showToast({ message: "Secret updated" }));
        router.push("/admin/secrets");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update secret");
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
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete secret");
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
        <AdminPageHeader title="Edit Secret" icon={KeyRound} />
        <FormColumn>
          <FormSkeleton fields={3} />
        </FormColumn>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="Edit Secret" icon={KeyRound} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" {...register("name")} />
          </FormField>

          <FormField htmlFor="type" label="Type" required>
            <Controller
              control={control}
              name="type"
              render={({ field }) => (
                <SegmentedControl
                  aria-label="Secret type"
                  options={[
                    { value: "local", label: "Local (encrypted)" },
                    { value: "vault", label: "HashiCorp Vault" },
                  ]}
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
          </FormField>

          {type === "local" ? (
            <FormField htmlFor="value" label="Value" error={errors.value?.message}>
              <Input
                id="value"
                type="password"
                autoComplete="off"
                placeholder="Leave blank to keep the current value"
                {...register("value")}
              />
            </FormField>
          ) : (
            <>
              <FormField
                htmlFor="vaultMount"
                label="Vault Mount"
                required
                error={errors.vaultMount?.message}
              >
                <Input id="vaultMount" placeholder="secret" {...register("vaultMount")} />
              </FormField>
              <FormField
                htmlFor="vaultPath"
                label="Vault Path"
                required
                error={errors.vaultPath?.message}
              >
                <Input id="vaultPath" placeholder="myapp/github" {...register("vaultPath")} />
              </FormField>
              <FormField
                htmlFor="vaultKey"
                label="Vault Key"
                required
                error={errors.vaultKey?.message}
              >
                <Input id="vaultKey" placeholder="token" {...register("vaultKey")} />
              </FormField>
            </>
          )}

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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/secrets")}>
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
        title="Delete Secret"
        description={`Delete "${getValues("name")}"? Anything still referencing it will fail at its next use.`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
