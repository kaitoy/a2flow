/** @module TenantField — Shared tenant picker used by the admin user create and edit forms. */
"use client";

import { useEffect, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { Select } from "@/components/ui/select";
import { listTenants, type Tenant } from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

/** Props for {@link TenantField}. */
export interface TenantFieldProps {
  /** Currently assigned tenant id, or `null` for an unassigned (platform-scoped) user. */
  value: string | null;
  /** Called with the next selection whenever the tenant changes. */
  onChange: (next: string | null) => void;
  /**
   * Whether the *target* user holds (or is about to hold) `super_admin`.
   * A super admin is platform-scoped by definition and must never carry a
   * tenant — the backend rejects the combination (HTTP 422) — so the select
   * is disabled and any previously chosen value is cleared via `onChange`.
   */
  disabled?: boolean;
  /**
   * Whether the target's tenant was already persisted (non-null) when this
   * form loaded. A tenant is immutable once assigned — the backend rejects
   * any change (HTTP 422) — so the select is disabled without touching
   * `value`, unlike `disabled`.
   */
  locked?: boolean;
}

/**
 * Tenant picker for the admin user forms, rendered as a labeled select.
 *
 * Only a super admin may assign a user's tenant — the backend rejects the
 * field otherwise (HTTP 403) — so the field renders nothing for any other
 * *viewer*, mirroring how {@link RolesField} disables its `super_admin`
 * checkbox for non-super-admins. Separately, the select becomes
 * non-interactive for two independent reasons: when the *target* user's
 * roles make them a super admin (`disabled`), where its value is also forced
 * back to `null` since a super admin can never carry a `tenant_id`; and when
 * the target already had a tenant assigned when the form loaded (`locked`),
 * where the value is left untouched since a tenant is immutable once set.
 */
export function TenantField({
  value,
  onChange,
  disabled = false,
  locked = false,
}: TenantFieldProps) {
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  const [tenants, setTenants] = useState<Tenant[]>([]);

  useEffect(() => {
    if (!isSuperAdmin) return;
    listTenants()
      .then(setTenants)
      .catch(() => {});
  }, [isSuperAdmin]);

  useEffect(() => {
    if (disabled && value !== null) onChange(null);
  }, [disabled, value, onChange]);

  if (!isSuperAdmin) return null;

  return (
    <FormField htmlFor="tenantId" label="Tenant">
      <Select
        id="tenantId"
        value={value ?? ""}
        disabled={disabled || locked}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">Unassigned</option>
        {tenants.map((tenant) => (
          <option key={tenant.id} value={tenant.id}>
            {tenant.name}
          </option>
        ))}
      </Select>
    </FormField>
  );
}
