/**
 * @module UserDetailPage — Admin edit/view form for an existing user.
 *
 * A tenant already assigned to the target is immutable (see `tenantId`
 * below), so this form never lets it be picked. For a still-tenant-less
 * target (a super admin being demoted, most commonly), the tenant to assign
 * is derived from the app bar's tenant picker (`auth.selectedTenantId`)
 * instead, the same as the create form.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Users as UsersIcon } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormColumn } from "@/components/admin/form-column";
import { FormField } from "@/components/admin/form-field";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { RolesField } from "@/components/admin/roles-field";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { zUserCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { type AvatarConfig, deleteUser, getUser, type UserUpdate, updateUser } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// Reuse the generated create-schema field constraints, but drop the immutable
// username and relax the password: on edit a blank value leaves the stored
// password unchanged, so empty string is allowed alongside the 12–72 range.
const schema = zUserCreate.omit({ username: true, password: true }).extend({
  password: z
    .string()
    .refine(
      (v) => v === "" || (v.length >= 12 && v.length <= 72),
      "Password must be 12–72 characters"
    ),
});

type FormValues = z.infer<typeof schema>;

export default function EditUserPage() {
  const { userId } = useParams<{ userId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // Username is immutable after creation, so it lives outside the form state and
  // is rendered read-only.
  const [username, setUsername] = useState("");
  // Avatar state, kept outside the form so the loaded avatar renders in a
  // read-only preview without touching the editable fields. Avatar editing is
  // self-service only (the account page); the admin form just displays the
  // current avatar. `avatarUpdatedAt` marks a custom uploaded image;
  // `avatarConfig` holds the user's Humation customization so the preview
  // matches their generated avatar elsewhere in the app.
  const [avatarUpdatedAt, setAvatarUpdatedAt] = useState<string | null>(null);
  const [avatarConfig, setAvatarConfig] = useState<AvatarConfig | null>(null);
  // Roles live outside the form state: the picker is a controlled multi-select
  // rather than a registered input.
  const [roles, setRoles] = useState<Role[]>([]);
  // The tenantId as loaded from the server. A tenant is immutable once
  // assigned (the backend rejects any change), so it's the source of truth
  // whenever it's non-null; `tenantId` below only derives a value from the
  // app bar's selection for a still-tenant-less target.
  const [originalTenantId, setOriginalTenantId] = useState<string | null>(null);
  const isSuperAdminViewer = useHasRole(Role.SUPER_ADMIN);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const tenantLocked = originalTenantId !== null;
  const targetIsSuperAdmin = roles.includes(Role.SUPER_ADMIN);
  const tenantId = tenantLocked
    ? originalTenantId
    : isSuperAdminViewer && !targetIsSuperAdmin
      ? selectedTenantId
      : null;
  // Only relevant for a still-tenant-less target being given a non-super-admin
  // role: the backend requires a tenant in that case, so block submission
  // instead of round-tripping to its 422.
  const tenantMissing =
    !tenantLocked && isSuperAdminViewer && !targetIsSuperAdmin && selectedTenantId === null;

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
      firstName: "",
      lastName: "",
      password: "",
      email: "",
      enabled: true,
      emailVerified: false,
    },
  });

  useEffect(() => {
    getUser(userId)
      .then((user) => {
        setUsername(user.username);
        setAvatarUpdatedAt(user.avatarUpdatedAt ?? null);
        setAvatarConfig(user.avatarConfig ?? null);
        setRoles(user.roles ?? []);
        setOriginalTenantId(user.tenantId ?? null);
        reset({
          firstName: user.firstName,
          lastName: user.lastName,
          password: "",
          email: user.email,
          enabled: user.enabled,
          emailVerified: user.emailVerified,
        });
        setAudit({
          createdBy: user.createdBy,
          updatedBy: user.updatedBy,
          createdAt: user.createdAt,
          updatedAt: user.updatedAt,
        });
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [userId, reset]);

  async function onSubmit(values: FormValues) {
    const body: UserUpdate = {
      firstName: values.firstName,
      lastName: values.lastName,
      email: values.email,
      enabled: values.enabled,
      emailVerified: values.emailVerified,
      roles,
      tenantId,
    };
    if (values.password) {
      body.password = values.password;
    }
    try {
      await save.run(async () => {
        await updateUser(userId, body);
        dispatch(showToast({ message: "User updated" }));
        router.push("/admin/users");
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
      await deleteUser(userId);
      router.push("/admin/users");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Users", href: "/admin/users" },
    { label: "Edit" },
  ];

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AdminPageHeader title="Edit User" icon={UsersIcon} />
        <FormColumn>
          <FormSkeleton fields={6} />
        </FormColumn>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="Edit User" icon={UsersIcon} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <div className="flex flex-col gap-1.5">
            <span className="text-label-caps">Avatar</span>
            <Avatar user={{ id: userId, username, avatarUpdatedAt, avatarConfig }} size={96} />
          </div>

          <FormField htmlFor="username" label="Username">
            <Input id="username" value={username} readOnly disabled />
          </FormField>

          <FormField
            htmlFor="firstName"
            label="First Name"
            required
            error={errors.firstName?.message}
          >
            <Input id="firstName" {...register("firstName")} />
          </FormField>

          <FormField htmlFor="lastName" label="Last Name" required error={errors.lastName?.message}>
            <Input id="lastName" {...register("lastName")} />
          </FormField>

          <FormField htmlFor="email" label="Email" required error={errors.email?.message}>
            <Input id="email" type="email" {...register("email")} />
          </FormField>

          <FormField htmlFor="password" label="Password" error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              placeholder="Leave blank to keep unchanged"
              {...register("password")}
            />
          </FormField>

          <RolesField value={roles} onChange={setRoles} />

          <Checkbox label="Enabled" {...register("enabled")} />
          <Checkbox label="Email verified" {...register("emailVerified")} />

          {tenantMissing && (
            <p className="text-xs text-error">
              Select a tenant in the header before removing this user's Super Admin role.
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
        title="Delete User"
        description={`Delete "${username}"?`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
