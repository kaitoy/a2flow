/**
 * @module TenantSettingsPage — Admin page for the settings a tenant's own
 * `admin` manages: today, how failed sign-ins lock the tenant's accounts.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import {
  SignInLockoutFields,
  signInLockoutShape,
  toSignInLockoutBody,
  toSignInLockoutFormValues,
} from "@/components/admin/sign-in-lockout-fields";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { getTenantSettings, SUPPRESS_FORBIDDEN_TOAST, updateTenantSettings } from "@/lib/api";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

const schema = z.object(signInLockoutShape);

type FormValues = z.infer<typeof schema>;

/**
 * Settings of the acting tenant: how many failed sign-ins lock one of its
 * accounts, and for how many minutes. Reachable only by `admin` (and
 * `super_admin`) — `layout.tsx` blocks every other viewer before this page
 * mounts.
 */
export default function TenantSettingsPage() {
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: toSignInLockoutFormValues({}),
  });

  useEffect(() => {
    getTenantSettings(SUPPRESS_FORBIDDEN_TOAST)
      .then((settings) => reset(toSignInLockoutFormValues(settings)))
      .catch(() => setDenied(true))
      .finally(() => setLoading(false));
  }, [reset]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        const saved = await updateTenantSettings(toSignInLockoutBody(values));
        reset(toSignInLockoutFormValues(saved));
        dispatch(showToast({ message: "Tenant settings updated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [{ label: "Home", href: "/" }, { label: "Tenant Settings" }];
  const header = <AdminPageHeader title="Tenant Settings" icon={ShieldCheck} />;

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={header}>
          <FormSkeleton fields={2} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  if (denied) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={header}>
          <p className="rounded-2xl glass-panel-strong p-6 text-on-surface-variant">
            The tenant settings could not be loaded.
          </p>
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout header={header}>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <SignInLockoutFields
            maxFailures={register("loginMaxFailures")}
            lockoutMinutes={register("loginLockoutMinutes")}
            errors={{
              loginMaxFailures: errors.loginMaxFailures?.message,
              loginLockoutMinutes: errors.loginLockoutMinutes?.message,
            }}
          />
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
          </div>
        </form>
      </FormLayout>
    </AdminPageContainer>
  );
}
