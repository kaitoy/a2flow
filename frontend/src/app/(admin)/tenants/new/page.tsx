/**
 * @module NewTenantPage — Admin form for creating a new tenant. Reachable
 * only by `super_admin` — `layout.tsx` blocks every other viewer before this
 * page mounts.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { zTenantCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useT } from "@/i18n/provider";
import { createTenant } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { tenantsChanged } from "@/store/tenantsSlice";
import { showToast } from "@/store/toastSlice";

const schema = zTenantCreate;

type FormValues = z.infer<typeof schema>;

export default function NewTenantPage() {
  const t = useT();
  const router = useRouter();
  const dispatch = useAppDispatch();

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      displayName: "",
      name: "",
      enabled: true,
    },
  });

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await createTenant({
          displayName: values.displayName,
          name: values.name,
          enabled: values.enabled,
        });
        dispatch(showToast({ message: t("tenants.tenantCreated") }));
        dispatch(tenantsChanged());
        router.push("/tenants");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: t("common.home"), href: "/" },
    { label: t("common.tenants"), href: "/tenants" },
    { label: t("common.new") },
  ];

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title={t("tenants.newTenant")} icon={Building2} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField
            htmlFor="displayName"
            label={t("tenants.displayName")}
            required
            error={errors.displayName?.message}
          >
            <Input
              id="displayName"
              placeholder={t("tenants.eGAcmeCorp")}
              {...register("displayName")}
            />
          </FormField>

          <FormField htmlFor="name" label={t("common.name")} required error={errors.name?.message}>
            <Input
              id="name"
              placeholder={t("tenants.lowercaseKebabCaseEGAcmeCorp")}
              {...register("name")}
            />
          </FormField>

          <Checkbox label={t("common.enabled")} {...register("enabled")} />

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight}
              status={save.status}
              pendingLabel={t("common.saving")}
            >
              {t("common.save")}
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/tenants")}>
              {t("common.cancel")}
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
