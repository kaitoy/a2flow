/** @module TenantDetailPage — Admin edit/view form for an existing tenant. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Building2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ErrorBanner } from "@/components/ui/error-banner";
import { Input } from "@/components/ui/input";
import { zTenantCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { deleteTenant, getTenant, type TenantUpdate, updateTenant } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

const schema = zTenantCreate;

type FormValues = z.infer<typeof schema>;

export default function EditTenantPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  const [name, setName] = useState("");

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
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

  useEffect(() => {
    getTenant(tenantId)
      .then((tenant) => {
        setName(tenant.name);
        reset({
          name: tenant.name,
          slug: tenant.slug,
          enabled: tenant.enabled,
        });
        setAudit({
          createdBy: tenant.createdBy,
          updatedBy: tenant.updatedBy,
          createdAt: tenant.createdAt,
          updatedAt: tenant.updatedAt,
        });
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : "Failed to load tenant");
      })
      .finally(() => setLoading(false));
  }, [tenantId, reset]);

  async function onSubmit(values: FormValues) {
    setApiError(null);
    const body: TenantUpdate = {
      name: values.name,
      slug: values.slug,
      enabled: values.enabled,
    };
    try {
      await save.run(async () => {
        await updateTenant(tenantId, body);
        dispatch(showToast({ message: "Tenant updated" }));
        router.push("/admin/tenants");
      });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to update tenant");
    }
  }

  function handleDelete() {
    setConfirmOpen(true);
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteTenant(tenantId);
      router.push("/admin/tenants");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Failed to delete tenant");
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Tenants", href: "/admin/tenants" },
    { label: "Edit" },
  ];

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AdminPageHeader title="Edit Tenant" icon={Building2} />
        <FormColumn>
          <FormSkeleton fields={3} />
        </FormColumn>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="Edit Tenant" icon={Building2} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" {...register("name")} />
          </FormField>

          <FormField htmlFor="slug" label="Slug" required error={errors.slug?.message}>
            <Input id="slug" {...register("slug")} />
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
        title="Delete Tenant"
        description={`Delete "${name}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
