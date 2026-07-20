/** @module NewTenantPage — Admin form for creating a new tenant. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { zTenantCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createTenant } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { tenantsChanged } from "@/store/tenantsSlice";
import { showToast } from "@/store/toastSlice";

const schema = zTenantCreate;

type FormValues = z.infer<typeof schema>;

export default function NewTenantPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [apiError, setApiError] = useState<string | null>(null);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      name: "",
      slug: "",
      enabled: true,
    },
  });

  async function onSubmit(values: FormValues) {
    setApiError(null);
    try {
      await save.run(async () => {
        await createTenant({
          name: values.name,
          slug: values.slug,
          enabled: values.enabled,
        });
        dispatch(showToast({ message: "Tenant created" }));
        dispatch(tenantsChanged());
        router.push("/admin/tenants");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to create tenant");
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Tenants", href: "/admin/tenants" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New Tenant" icon={Building2} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" placeholder="e.g. Acme Corp" {...register("name")} />
          </FormField>

          <FormField htmlFor="slug" label="Slug" required error={errors.slug?.message}>
            <Input
              id="slug"
              placeholder="Lowercase kebab-case, e.g. acme-corp"
              {...register("slug")}
            />
          </FormField>

          <Checkbox label="Enabled" {...register("enabled")} />

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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/tenants")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
