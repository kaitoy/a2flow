/**
 * @module NewUserPage — Admin form for creating a new application user.
 *
 * The tenant a new user belongs to is not picked in this form — it's derived
 * from the app bar's tenant picker (`auth.selectedTenantId`), the same tenant
 * every other request already acts as. See `tenantId` below.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Users as UsersIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { RolesField } from "@/components/admin/roles-field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { zUserCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createUser } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

const schema = zUserCreate;

type FormValues = z.infer<typeof schema>;

export default function NewUserPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  // Roles live outside the form state: the picker is a controlled multi-select
  // rather than a registered input.
  const [roles, setRoles] = useState<Role[]>([]);
  const isSuperAdminViewer = useHasRole(Role.SUPER_ADMIN);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const targetIsSuperAdmin = roles.includes(Role.SUPER_ADMIN);
  // A plain admin's own tenant is applied server-side regardless of what's
  // sent, so only a super admin's app-bar selection is ever meaningful here.
  // A super admin is always platform-scoped, so granting that role forces
  // null no matter what tenant is currently selected in the app bar.
  const tenantId = isSuperAdminViewer && !targetIsSuperAdmin ? selectedTenantId : null;
  // Only a super admin creating a non-super-admin user needs a tenant; block
  // submission instead of round-tripping to the backend's 422 for this case.
  const tenantMissing = isSuperAdminViewer && !targetIsSuperAdmin && selectedTenantId === null;

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: {
      username: "",
      firstName: "",
      lastName: "",
      password: "",
      email: "",
      enabled: true,
      emailVerified: false,
    },
  });

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await createUser({
          username: values.username,
          firstName: values.firstName,
          lastName: values.lastName,
          password: values.password,
          email: values.email,
          enabled: values.enabled,
          emailVerified: values.emailVerified,
          roles,
          tenantId,
        });
        dispatch(showToast({ message: "User created" }));
        router.push("/admin/users");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs
        items={[
          { label: "Admin", href: "/admin" },
          { label: "Users", href: "/admin/users" },
          { label: "New" },
        ]}
      />
      <AdminPageHeader title="New User" icon={UsersIcon} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="username" label="Username" required error={errors.username?.message}>
            <Input id="username" placeholder="e.g. alice" {...register("username")} />
          </FormField>

          <FormField
            htmlFor="firstName"
            label="First Name"
            required
            error={errors.firstName?.message}
          >
            <Input id="firstName" placeholder="Alice" {...register("firstName")} />
          </FormField>

          <FormField htmlFor="lastName" label="Last Name" required error={errors.lastName?.message}>
            <Input id="lastName" placeholder="Smith" {...register("lastName")} />
          </FormField>

          <FormField htmlFor="email" label="Email" required error={errors.email?.message}>
            <Input id="email" type="email" placeholder="alice@example.com" {...register("email")} />
          </FormField>

          <FormField htmlFor="password" label="Password" required error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              placeholder="At least 12 characters"
              {...register("password")}
            />
          </FormField>

          <RolesField value={roles} onChange={setRoles} />

          <Checkbox label="Enabled" {...register("enabled")} />
          <Checkbox label="Email verified" {...register("emailVerified")} />

          {tenantMissing && (
            <p className="text-xs text-error">
              Select a tenant in the header before creating this user.
            </p>
          )}

          <div className="flex gap-2">
            <Button
              type="submit"
              variant="primary"
              disabled={save.inFlight || tenantMissing}
              status={save.status}
              pendingLabel="Saving…"
            >
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/users")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
