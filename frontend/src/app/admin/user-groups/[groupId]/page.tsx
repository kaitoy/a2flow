/** @module UserGroupDetailPage — Admin detail page for an existing user group. */
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { UsersRound } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import type { z } from "zod";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta, type AuditMetaProps } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormField } from "@/components/admin/form-field";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { RolesField } from "@/components/admin/roles-field";
import { TagPicker } from "@/components/admin/tag-picker";
import { UserPicker } from "@/components/admin/user-picker";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { zUserGroupCreate } from "@/generated/api/zod.gen";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import {
  deleteUserGroup,
  getUserGroup,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
  setUserGroupTags,
  updateUserGroup,
} from "@/lib/api";
import { sameIds } from "@/lib/ids";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { Role, useHasRole } from "@/lib/roles";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

// roles and memberIds are controlled multi-selects rather than registered
// inputs, so they are kept out of the form schema and merged at submit.
const schema = zUserGroupCreate.omit({ roles: true, memberIds: true });

type FormValues = z.input<typeof schema>;

/**
 * Detail page of a user group: its name, description, the roles it grants, and
 * its members.
 *
 * Changing the roles or the membership takes effect for every affected user on
 * their very next request — inherited roles are resolved live rather than
 * stored on the user, so there is nothing to re-sync afterwards.
 *
 * A viewer without the admin role gets a read-only rendering — reads are open to
 * every authenticated user, but every group write is admin-only — so the fields
 * show as plain values and Save/Delete are hidden rather than left to fail with
 * a 403 on click.
 */
export default function UserGroupDetailPage() {
  const { groupId } = useParams<{ groupId: string }>();
  const router = useRouter();
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.ADMIN);
  const isAllTenantsView = useIsAllTenantsView();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [audit, setAudit] = useState<AuditMetaProps | null>(null);
  // The persisted name, which titles the page. Kept out of the form so the
  // heading names the saved record rather than following every keystroke.
  const [name, setName] = useState("");
  const [roles, setRoles] = useState<Role[]>([]);
  const [memberIds, setMemberIds] = useState<string[]>([]);
  // `savedTagIds` is what the last successful save wrote, so a submit only
  // re-PUTs the tag set when it actually changed.
  const [tagIds, setTagIds] = useState<string[]>([]);
  const [savedTagIds, setSavedTagIds] = useState<string[]>([]);

  const save = useAsyncAction({ showDone: false });
  const {
    register,
    handleSubmit,
    reset,
    getValues,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    mode: "onBlur",
    defaultValues: { name: "", description: "" },
  });

  useEffect(() => {
    getUserGroup(groupId, SUPPRESS_FORBIDDEN_TOAST)
      .then((group) => {
        setName(group.name);
        setRoles(group.roles ?? []);
        setMemberIds(group.memberIds ?? []);
        setTagIds(group.tagIds ?? []);
        setSavedTagIds(group.tagIds ?? []);
        reset({ name: group.name, description: group.description ?? "" });
        setAudit({
          createdBy: group.createdBy,
          updatedBy: group.updatedBy,
          createdAt: group.createdAt,
          updatedAt: group.updatedAt,
          tenantId: isAllTenantsView ? group.tenantId : undefined,
        });
      })
      .catch((err: unknown) => {
        if (isForbiddenError(err)) {
          setForbidden(true);
          return;
        }
        // Failure toast is shown globally by api.ts; nothing else to do here.
      })
      .finally(() => setLoading(false));
  }, [groupId, reset, isAllTenantsView]);

  async function onSubmit(values: FormValues) {
    try {
      await save.run(async () => {
        await updateUserGroup(groupId, {
          name: values.name,
          description: values.description || null,
          roles,
          memberIds,
        });
        // Tags are a separate sub-resource, written only when the selection
        // actually changed.
        if (!sameIds(tagIds, savedTagIds)) {
          await setUserGroupTags(groupId, tagIds);
        }
        dispatch(showToast({ message: "User group updated" }));
        router.push("/admin/user-groups");
      });
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  async function executeDelete() {
    setConfirmOpen(false);
    try {
      await deleteUserGroup(groupId);
      router.push("/admin/user-groups");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
    }
  }

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "User Groups", href: "/admin/user-groups" },
    // The group itself is the current page; an ellipsis stands in until its
    // name has loaded.
    { label: name || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={UsersRound} />}>
          <FormSkeleton fields={4} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={name} icon={UsersRound} />}
        aside={audit && <AuditMeta {...audit} />}
      >
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6"
        >
          <FormField htmlFor="name" label="Name" required error={errors.name?.message}>
            {canEdit ? (
              <Input id="name" {...register("name")} />
            ) : (
              <ReadOnlyField>{name || EMPTY_VALUE}</ReadOnlyField>
            )}
          </FormField>

          <FormField htmlFor="description" label="Description" error={errors.description?.message}>
            {canEdit ? (
              <Textarea id="description" rows={2} {...register("description")} />
            ) : (
              <ReadOnlyField>{getValues("description") || EMPTY_VALUE}</ReadOnlyField>
            )}
          </FormField>

          {/* A group can never grant super_admin; the backend rejects it with 422. */}
          <RolesField
            value={roles}
            onChange={setRoles}
            readOnly={!canEdit}
            allowSuperAdmin={false}
            label="Roles granted"
          />

          <UserPicker value={memberIds} onChange={setMemberIds} readOnly={!canEdit} />

          <TagPicker value={tagIds} onChange={setTagIds} readOnly={!canEdit} />

          <div className="flex gap-2">
            {canEdit && (
              <Button
                type="submit"
                variant="primary"
                disabled={save.inFlight}
                status={save.status}
                pendingLabel="Saving…"
              >
                Save
              </Button>
            )}
            <Button type="button" variant="ghost" onClick={() => router.push("/admin/user-groups")}>
              {canEdit ? "Cancel" : "Back"}
            </Button>
            {canEdit && (
              <Button
                type="button"
                variant="danger"
                onClick={() => setConfirmOpen(true)}
                className="ml-auto"
              >
                Delete
              </Button>
            )}
          </div>
        </form>
      </FormLayout>
      <ConfirmDialog
        open={confirmOpen}
        title="Delete User Group"
        description={`Delete "${name}"? Its members keep their accounts but lose the roles it grants.`}
        onConfirm={executeDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </AdminPageContainer>
  );
}
