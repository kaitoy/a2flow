/**
 * @module NewUserGroupPage — Admin form for creating a user group.
 *
 * The tenant a group belongs to is not picked in this form — it's derived from
 * the app bar's tenant picker (`auth.selectedTenantId`), the same tenant every
 * other request already acts as, exactly as the new-user form does it.
 */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { UsersRound } from "lucide-react";
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
import { TagPicker } from "@/components/admin/tag-picker";
import { UserPicker } from "@/components/admin/user-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zUserGroupCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { createUserGroup, setUserGroupTags } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

const schema = zUserGroupCreate;

type FormValues = z.input<typeof schema>;

export default function NewUserGroupPage() {
  const router = useRouter();
  const dispatch = useAppDispatch();
  // Roles, members, and tags live outside the form state: all are controlled
  // multi-selects rather than registered inputs, and tags are a sub-resource
  // written after the group exists.
  const [roles, setRoles] = useState<Role[]>([]);
  const [memberIds, setMemberIds] = useState<string[]>([]);
  const [tagIds, setTagIds] = useState<string[]>([]);
  const isSuperAdminViewer = useHasRole(Role.SUPER_ADMIN);
  const canEdit = useHasRole(Role.ADMIN);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  // A plain admin's own tenant is applied server-side regardless, so only a
  // super admin's app-bar selection is ever meaningful here.
  const tenantMissing = isSuperAdminViewer && selectedTenantId === null;

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", description: "" },
  });

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        const created = await createUserGroup({
          name: values.name,
          description: values.description || null,
          roles,
          memberIds,
        });
        if (tagIds.length > 0) {
          await setUserGroupTags(created.id, tagIds);
        }
        dispatch(showToast({ message: "User group created" }));
        router.push("/admin/user-groups");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "User Groups", href: "/admin/user-groups" },
    { label: "New" },
  ];

  // The list page hides the Add button for this viewer, so reaching the form at
  // all means a deep link; refuse it here rather than let the submit 403.
  if (!canEdit) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <AdminPageHeader title="New User Group" icon={UsersRound} />

      <FormColumn>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            <Input id="name" placeholder="e.g. Developers" {...register("name")} />
          </FormField>

          <FormField htmlFor="description" label="Description" error={errors.description?.message}>
            <Textarea
              id="description"
              rows={2}
              placeholder="What this group is for"
              {...register("description")}
            />
          </FormField>

          {/* A group can never grant super_admin; the backend rejects it with 422. */}
          <RolesField
            value={roles}
            onChange={setRoles}
            allowSuperAdmin={false}
            label="Roles granted"
          />

          <UserPicker value={memberIds} onChange={setMemberIds} />

          <TagPicker value={tagIds} onChange={setTagIds} />

          {tenantMissing && (
            <p className="text-xs text-error">
              Select a tenant in the header before creating this group.
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
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/user-groups")}>
              Cancel
            </Button>
          </div>
        </form>
      </FormColumn>
    </AdminPageContainer>
  );
}
