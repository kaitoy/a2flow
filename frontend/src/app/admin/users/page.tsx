/**
 * @module UsersPage — Admin list page for managing application users.
 *
 * Reads are open to every authenticated user within the tenant, so a viewer
 * without the admin role sees the list but neither the Add button nor the
 * Actions column — the same convention the detail page follows by rendering
 * read-only.
 */
"use client";

import { UserCog, User as UsersIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ActionIconButton } from "@/components/admin/action-icon-button";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { auditColumns, idColumn } from "@/components/admin/audit-columns";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { ColumnPicker } from "@/components/admin/column-picker";
import { DeleteIconButton } from "@/components/admin/delete-icon-button";
import { InheritedRoles } from "@/components/admin/inherited-roles";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { tenantColumn } from "@/components/admin/tenant-columns";
import { USER_SHARED_COLUMNS } from "@/components/admin/user-columns";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  BOOL_FILTER_OPTIONS,
  boolCell,
  type ColumnDef,
  DataTable,
} from "@/components/ui/data-table";
import { DateTime } from "@/components/ui/date-time";
import { useColumnVisibility } from "@/hooks/useColumnVisibility";
import { useIsAllTenantsView } from "@/hooks/useIsAllTenantsView";
import { useTableQuery } from "@/hooks/useTableQuery";
import { useTenantNames } from "@/hooks/useTenantNames";
import { useUserNames } from "@/hooks/useUserNames";
import { deleteUser, listUsers, startImpersonation, type User } from "@/lib/api";
import { canImpersonate, persistImpersonatedUserId } from "@/lib/impersonation";
import { ROLE_LABELS, Role, useHasRole } from "@/lib/roles";
import { setMe } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

const LIMIT = 20;

/**
 * Columns of the list table. Avatar, Username, Roles, Enabled, Verified, and
 * Created At are local to this page — Username links off to the user's detail
 * page, which the picker dialog never does — Name and Email are shared with
 * {@link UserPicker}'s dialog table via {@link USER_SHARED_COLUMNS}. Takes
 * `names` (rather than being a static array) because the audit columns need it.
 */
function buildColumns(
  names: Map<string, string>,
  tenantNames: Map<string, string>,
  isAllTenantsView: boolean
): ColumnDef<User>[] {
  return [
    ...(isAllTenantsView ? [tenantColumn<User>(tenantNames)] : []),
    idColumn<User>(),
    {
      header: "",
      noTruncate: true,
      visibility: "always",
      cell: (u) => <Avatar user={u} size={28} />,
    },
    {
      header: "Username",
      sortField: "username",
      filterField: "username",
      visibility: "always",
      cell: (u) => (
        <Link
          href={`/admin/users/${u.id}`}
          className="font-medium text-accent transition-colors hover:underline"
        >
          {u.username}
        </Link>
      ),
    },
    ...USER_SHARED_COLUMNS,
    {
      // Roles are stored as a JSON list, which the list API's sort/filter params
      // cannot address, so this column is display-only — and the same goes for
      // the group-inherited half. The Super Admin badge and the inherited chips
      // are chips, not plain text, so the column opts out of single-line
      // truncation. Inherited roles render as muted chips so it stays obvious
      // which grants editing the user can actually change.
      header: "Roles",
      noTruncate: true,
      cell: (u) => {
        const isSuperAdmin = u.roles?.includes(Role.SUPER_ADMIN);
        const otherRoles = (u.roles ?? []).filter((r) => r !== Role.SUPER_ADMIN);
        const groupRoles = u.groupRoles ?? [];
        const nothingHeld = !isSuperAdmin && otherRoles.length === 0 && groupRoles.length === 0;
        return (
          <div className="flex items-center gap-1.5">
            {isSuperAdmin && <Badge>Super Admin</Badge>}
            {otherRoles.length > 0 && (
              <span>{otherRoles.map((r) => ROLE_LABELS[r]).join(", ")}</span>
            )}
            <InheritedRoles roles={groupRoles} />
            {nothingHeld && "—"}
          </div>
        );
      },
    },
    {
      header: "Enabled",
      sortField: "enabled",
      filterField: "enabled",
      filterOp: "eq",
      filterOptions: BOOL_FILTER_OPTIONS,
      className: "text-center",
      cell: (u) => boolCell(u.enabled),
    },
    {
      header: "Verified",
      sortField: "emailVerified",
      filterField: "emailVerified",
      filterOp: "eq",
      filterOptions: BOOL_FILTER_OPTIONS,
      className: "text-center",
      visibility: "optional",
      cell: (u) => boolCell(u.emailVerified),
    },
    {
      header: "Created At",
      sortField: "createdAt",
      visibility: "optional",
      cell: (u) => <DateTime value={u.createdAt} className="text-on-surface-variant" />,
    },
    {
      header: "Deleted At",
      visibility: "optional",
      cell: (u) =>
        u.deletedAt ? <DateTime value={u.deletedAt} className="text-on-surface-variant" /> : "—",
    },
    ...auditColumns<User>(names),
  ];
}

export default function UsersPage() {
  const {
    rows,
    loading,
    refreshing,
    offset,
    sort,
    filters,
    setOffset,
    setSort,
    setFilters,
    reload,
  } = useTableQuery<User>(listUsers, { limit: LIMIT });
  const names = useUserNames(rows.flatMap((u) => [u.createdBy, u.updatedBy]));
  const isAllTenantsView = useIsAllTenantsView();
  // Only resolved when the Tenant column is actually rendered: the lookup goes
  // through the super_admin-only tenants list, so asking for it as a plain
  // admin spends a request that can only come back 403 — and toasts.
  const tenantNames = useTenantNames(isAllTenantsView ? rows.map((u) => u.tenantId) : []);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string; name: string } | null>(null);
  const [impersonateTarget, setImpersonateTarget] = useState<{ id: string; name: string } | null>(
    null
  );
  const router = useRouter();
  const dispatch = useAppDispatch();
  const viewer = useAppSelector((s) => s.auth.user);
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  // `useHasRole` passes for super_admin too (its bypass), but by the time this
  // matters below `isSuperAdmin` has already been checked first, so here it
  // can only mean "genuinely holds admin, not super_admin".
  const isAdmin = useHasRole(Role.ADMIN);

  function handleDelete(id: string, name: string) {
    setConfirmTarget({ id, name });
  }

  async function executeDelete() {
    if (!confirmTarget) return;
    try {
      await deleteUser(confirmTarget.id);
      setConfirmTarget(null);
      await reload();
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setConfirmTarget(null);
    }
  }

  function handleImpersonate(id: string, name: string) {
    setImpersonateTarget({ id, name });
  }

  async function executeImpersonate() {
    if (!impersonateTarget) return;
    try {
      const me = await startImpersonation(impersonateTarget.id);
      dispatch(setMe(me));
      persistImpersonatedUserId(me.user.id);
      setImpersonateTarget(null);
      router.push("/admin");
    } catch {
      // Failure toast is shown globally by api.ts; nothing else to do here.
      setImpersonateTarget(null);
    }
  }

  const columns: ColumnDef<User>[] = [
    ...buildColumns(names, tenantNames, isAllTenantsView),
    // Both actions in this column need the admin role — deleting a user
    // outright, and `canImpersonate`, which already answers false without it —
    // so the whole column goes for a viewer who only holds a read role.
    ...(isAdmin
      ? [
          {
            header: "Actions",
            noTruncate: true,
            visibility: "always" as const,
            cell: (user: User) => (
              <div className="flex justify-center gap-2">
                {canImpersonate(viewer, isSuperAdmin, isAdmin, user) && (
                  <ActionIconButton
                    icon={UserCog}
                    label="Impersonate"
                    onClick={() => handleImpersonate(user.id, user.username)}
                  />
                )}
                <DeleteIconButton onClick={() => handleDelete(user.id, user.username)} />
              </div>
            ),
          },
        ]
      : []),
  ];

  const { visibleColumns, options, selected, setSelected, reset, customized } = useColumnVisibility(
    "users",
    columns
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Users" }]} />
      <AdminPageHeader
        title="Users"
        icon={UsersIcon}
        addHref={isAdmin ? "/admin/users/new" : undefined}
        addLabel="+ Add user"
        onRefresh={reload}
        refreshing={loading || refreshing}
        columnPicker={
          <ColumnPicker
            options={options}
            value={selected}
            onChange={setSelected}
            onReset={reset}
            customized={customized}
          />
        }
      />
      <DataTable
        columns={visibleColumns}
        rows={rows}
        loading={loading}
        emptyMessage="No users registered yet."
        emptyIcon={UsersIcon}
        getRowKey={(user) => user.id}
        sort={sort}
        onSortChange={setSort}
        filters={filters}
        onFilterChange={setFilters}
      />
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={rows.length}
        onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
        onNext={() => setOffset((o) => o + LIMIT)}
      />
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Delete User"
        description={confirmTarget ? `Delete "${confirmTarget.name}"?` : ""}
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
      <ConfirmDialog
        open={impersonateTarget !== null}
        title="Impersonate User"
        description={
          impersonateTarget ? `Act as "${impersonateTarget.name}"? You can stop at any time.` : ""
        }
        confirmLabel="Impersonate"
        confirmVariant="primary"
        onConfirm={executeImpersonate}
        onCancel={() => setImpersonateTarget(null)}
      />
    </AdminPageContainer>
  );
}
