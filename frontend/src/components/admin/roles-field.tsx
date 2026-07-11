/** @module RolesField — Shared roles multi-select used by the admin user create and edit forms. */
"use client";

import { CheckboxGroup, type CheckboxOption } from "@/components/ui/checkbox-group";
import { ALL_ROLES, ROLE_LABELS, Role, useHasRole } from "@/lib/roles";

/** Props for {@link RolesField}. */
export interface RolesFieldProps {
  /** Currently selected roles. */
  value: Role[];
  /** Called with the next selection whenever a role is toggled. */
  onChange: (next: Role[]) => void;
}

/**
 * Role picker for the admin user forms, rendered as a labeled checkbox group.
 *
 * The `super_admin` checkbox is disabled unless the signed-in user is a super
 * admin — the backend rejects granting or revoking it otherwise (HTTP 403), so
 * the control mirrors that rule. A target's existing `super_admin` role stays
 * checked (and is submitted unchanged) even while disabled.
 */
export function RolesField({ value, onChange }: RolesFieldProps) {
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);

  const options: CheckboxOption[] = ALL_ROLES.map((role) => ({
    value: role,
    label: ROLE_LABELS[role],
    disabled: role === Role.SUPER_ADMIN && !isSuperAdmin,
  }));

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">Roles</span>
      <CheckboxGroup
        name="roles"
        options={options}
        value={value}
        onChange={(next) => onChange(next as Role[])}
      />
    </div>
  );
}
