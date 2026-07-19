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
 * The `super_admin` option is omitted entirely for a non-super-admin viewer —
 * the backend rejects granting or revoking it otherwise (HTTP 403), and only a
 * super admin should even know the role exists. A target's existing
 * `super_admin` grant is preserved and submitted unchanged even though its
 * checkbox isn't rendered: {@link CheckboxGroup} otherwise reconstructs its
 * reported selection from the rendered options alone, so toggling any other
 * role would silently drop the grant — `handleChange` re-adds it whenever it
 * was already held but missing from what `CheckboxGroup` reported back.
 */
export function RolesField({ value, onChange }: RolesFieldProps) {
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);

  const visibleRoles = isSuperAdmin
    ? ALL_ROLES
    : ALL_ROLES.filter((role) => role !== Role.SUPER_ADMIN);
  const options: CheckboxOption[] = visibleRoles.map((role) => ({
    value: role,
    label: ROLE_LABELS[role],
  }));

  function handleChange(next: string[]) {
    const keepsSuperAdmin =
      !isSuperAdmin && value.includes(Role.SUPER_ADMIN) && !next.includes(Role.SUPER_ADMIN);
    onChange((keepsSuperAdmin ? [...next, Role.SUPER_ADMIN] : next) as Role[]);
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">Roles</span>
      <CheckboxGroup name="roles" options={options} value={value} onChange={handleChange} />
    </div>
  );
}
