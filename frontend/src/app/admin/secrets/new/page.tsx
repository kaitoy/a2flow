/** @module NewSecretPage — Admin form for registering a new secret (local encrypted value or Vault reference). */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { zSecretCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createSecret } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// The generated schema marks the per-type fields nullish with min-length 1, so
// a hidden empty input would fail validation. The form instead keeps them as
// plain strings and enforces the per-type requiredness itself, mirroring the
// backend's shape validation.
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
    if (v.type === "local" && v.value === "") {
      ctx.addIssue({ code: "custom", path: ["value"], message: "Value is required" });
    }
    if (v.type === "vault") {
      for (const field of ["vaultMount", "vaultPath", "vaultKey"] as const) {
        if (v[field] === "") {
          ctx.addIssue({ code: "custom", path: [field], message: "Required for a Vault secret" });
        }
      }
    }
  });

type FormValues = z.infer<typeof schema>;

export default function NewSecretPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [apiError, setApiError] = useState<string | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    control,
    watch,
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

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await createSecret(
          values.type === "local"
            ? { name: values.name, type: "local", value: values.value }
            : {
                name: values.name,
                type: "vault",
                vaultMount: values.vaultMount,
                vaultPath: values.vaultPath,
                vaultKey: values.vaultKey,
              }
        );
        dispatch(showToast({ message: "Secret created" }));
        router.push("/admin/secrets");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create secret");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Secrets", href: "/admin/secrets" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Secret" icon={KeyRound} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" placeholder="e.g. github-token" {...register("name")} />
            <p className="mt-1 text-xs text-on-surface-variant">
              Referenced as{" "}
              {/* biome-ignore lint/suspicious/noTemplateCurlyInString: literal placeholder syntax shown to the user */}
              {"${secret:name}"} in MCP server headers and by name in Agent Skill repo auth.
            </p>
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
            <FormField htmlFor="value" label="Value" required error={errors.value?.message}>
              <Input
                id="value"
                type="password"
                autoComplete="off"
                placeholder="Secret value (stored encrypted)"
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
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
