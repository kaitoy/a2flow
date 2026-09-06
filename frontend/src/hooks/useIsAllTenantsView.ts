/** @module useIsAllTenantsView — whether a Super Admin is currently browsing every tenant at once. */
"use client";

import { ALL_TENANTS_SENTINEL } from "@/store/authSlice";
import { useAppSelector } from "@/store/hooks";

/**
 * Whether the acting tenant selection is the "All tenants" sentinel — i.e. the
 * viewer is a Super Admin browsing every tenant's data at once rather than one
 * tenant's. Pages use this to decide whether a Tenant column/field, otherwise
 * redundant when every row shares one tenant, earns its place on screen.
 *
 * Always `false` while an impersonation is active: a valid impersonation target
 * is always tenant-scoped, so the backend scopes every request to that user's
 * tenant and ignores the `X-Tenant-Id` header (see
 * `dependencies.auth.get_current_tenant_scope`). "All tenants" is therefore
 * never genuinely in effect during impersonation, even though the Super Admin's
 * selection still reads as the sentinel and resumes once they stop.
 *
 * @returns `true` while "All tenants" is selected in the header's
 *   `TenantSwitcher` and no impersonation is active.
 */
export function useIsAllTenantsView(): boolean {
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const impersonatedBy = useAppSelector((s) => s.auth.impersonatedBy);
  return !impersonatedBy && selectedTenantId === ALL_TENANTS_SENTINEL;
}
