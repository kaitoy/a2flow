/** @module TenantSwitcher — Header control letting a Super Admin pick which tenant to act as. */
"use client";

import { useEffect, useState } from "react";
import { Select } from "@/components/ui/select";
import { listTenants, type Tenant } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";
import { SELECTED_TENANT_STORAGE_KEY, setSelectedTenantId } from "@/store/authSlice";
import { useAppDispatch, useAppSelector } from "@/store/hooks";

/** Persist a tenant selection to localStorage, ignoring privacy-mode write failures. */
function persistSelection(tenantId: string | null): void {
  try {
    if (tenantId) {
      window.localStorage.setItem(SELECTED_TENANT_STORAGE_KEY, tenantId);
    } else {
      window.localStorage.removeItem(SELECTED_TENANT_STORAGE_KEY);
    }
  } catch {
    // Ignore -- privacy-mode browsers may throw on localStorage writes.
  }
}

/**
 * Tenant picker rendered in the app header for a signed-in Super Admin.
 *
 * A Super Admin has no tenant of their own, but nearly every resource
 * (agent skills, workflows, secrets, MCP servers, workflow sessions, chat)
 * belongs to one — so this lets them pick which tenant to "act as." The
 * selection is sent as the `X-Tenant-Id` header on every API request (see
 * `lib/api.ts`), remembered across reloads, and auto-selects the first
 * available tenant the first time a Super Admin signs in (or if a previously
 * persisted tenant no longer exists). Renders nothing for any other viewer.
 *
 * An explicit change from the dropdown reloads the page: every admin list
 * page fetches its data once on mount with no dependency on the selected
 * tenant, so without a reload an already-open page (e.g. Agent Skills) would
 * keep showing the previous tenant's rows -- correct once refreshed, but
 * silently stale until then. A full reload is the simplest way to make every
 * open page's data match the newly selected tenant. The initial auto-select
 * doesn't reload: nothing has been displayed yet, so there's no stale data to
 * invalidate.
 *
 * The tenant *list* itself is re-fetched whenever `tenants.version` in Redux
 * changes, not just on mount -- tenant CRUD pages dispatch `tenantsChanged()`
 * on success so this picker (which lives in the persistent admin layout and
 * therefore doesn't remount on client-side navigation) reflects new/renamed/
 * deleted tenants without requiring a reload.
 */
export function TenantSwitcher() {
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  const dispatch = useAppDispatch();
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const tenantsVersion = useAppSelector((s) => s.tenants.version);
  const [tenants, setTenants] = useState<Tenant[]>([]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: tenantsVersion is a bump counter that re-triggers the fetch, not a data dependency
  useEffect(() => {
    if (!isSuperAdmin) return;
    listTenants()
      .then(setTenants)
      .catch(() => {});
  }, [isSuperAdmin, tenantsVersion]);

  useEffect(() => {
    if (!isSuperAdmin || tenants.length === 0) return;
    if (selectedTenantId && tenants.some((t) => t.id === selectedTenantId)) return;
    const fallback = tenants.find((t) => t.enabled) ?? tenants[0];
    dispatch(setSelectedTenantId(fallback.id));
    persistSelection(fallback.id);
  }, [isSuperAdmin, tenants, selectedTenantId, dispatch]);

  if (!isSuperAdmin) return null;

  return (
    <Select
      aria-label="Acting tenant"
      value={selectedTenantId ?? ""}
      disabled={tenants.length === 0}
      onChange={(next) => {
        persistSelection(next || null);
        dispatch(setSelectedTenantId(next || null));
        window.location.reload();
      }}
      options={
        tenants.length === 0
          ? [{ value: "", label: "No tenants" }]
          : tenants.map((tenant) => ({ value: tenant.id, label: tenant.displayName }))
      }
      className="w-auto min-w-32"
    />
  );
}
