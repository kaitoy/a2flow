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
 * @returns `true` while "All tenants" is selected in the header's `TenantSwitcher`.
 */
export function useIsAllTenantsView(): boolean {
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  return selectedTenantId === ALL_TENANTS_SENTINEL;
}
