/** @module RolesField — Shared roles multi-select used by the admin user create and edit forms. */
"use client";

import { ReadOnlyField } from "@/components/admin/read-only-field";
import { CheckboxGroup, type CheckboxOption } from "@/components/ui/checkbox-group";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { ALL_ROLES, ROLE_LABELS, Role, useHasRole } from "@/lib/roles";

/** Props for {@link RolesField}. */
export interface RolesFieldProps {
  /** Currently selected roles. */
  value: Role[];
  /** Called with the next selection whenever a role is toggled. */
  onChange: (next: Role[]) => void;
  /**
   * Renders the held roles as a value instead of a checkbox group, for a viewer
   * whose role cannot write users. `onChange` is then never called.
   */
  readOnly?: boolean;
  /**
   * Whether `super_admin` may appear as an option at all. `false` for the user
   * group forms: a group can never grant it, and the backend rejects the
   * attempt with HTTP 422.
   */
  allowSuperAdmin?: boolean;
  /** Label above the group; distinguishes direct grants from inherited ones. */
  label?: string;
}

/**
 * Role picker for the admin user forms, rendered as a labeled checkbox group.
 *
 * The `super_admin` option is omitted entirely for a non-super-admin viewer —
 * the backend rejects granting or revoking it otherwise (HTTP 403), and only a
 * super admin should even know the role exists. The same filter applies to the
 * read-only rendering, so no viewer learns of a role they may not see. Callers
 * that grant roles to something other than a user pass `allowSuperAdmin={false}`
 * to drop the option for every viewer — a user group can never grant it.
 *
 * These are the roles held *directly*. Roles a user inherits from their groups
 * are rendered apart by {@link InheritedRolesField}, since editing the user
 * cannot change them.
 *
 * `super_admin` is mutually exclusive with every other role (it already
 * bypasses every role-based check, so combining it with another role is
 * redundant). Rather than silently dropping a selection, checking either side
 * disables the other: once `super_admin` is held, every other checkbox is
 * disabled (and vice versa), with a divider and hint explaining why. A
 * non-super-admin viewer editing a target that already holds `super_admin`
 * therefore sees every rendered checkbox disabled — the `super_admin`
 * checkbox itself stays hidden from them, but nothing else can be toggled
 * until a super admin lifts the grant.
 */
export function RolesField({
  value,
  onChange,
  readOnly = false,
  allowSuperAdmin = true,
  label = "Roles",
}: RolesFieldProps) {
  const viewerIsSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  const showSuperAdmin = allowSuperAdmin && viewerIsSuperAdmin;

  const visibleRoles = showSuperAdmin
    ? ALL_ROLES
    : ALL_ROLES.filter((role) => role !== Role.SUPER_ADMIN);

  if (readOnly) {
    const held = visibleRoles.filter((role) => value.includes(role));
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-label-caps">{label}</span>
        <ReadOnlyField>
          {held.length === 0 ? EMPTY_VALUE : held.map((role) => ROLE_LABELS[role]).join(", ")}
        </ReadOnlyField>
      </div>
    );
  }

  const holdsSuperAdmin = value.includes(Role.SUPER_ADMIN);
  const holdsOtherRole = value.some((role) => role !== Role.SUPER_ADMIN);

  const options: CheckboxOption[] = visibleRoles.map((role, i) => ({
    value: role,
    label: ROLE_LABELS[role],
    disabled: role === Role.SUPER_ADMIN ? holdsOtherRole : holdsSuperAdmin,
    dividerBefore: showSuperAdmin && i === 1,
  }));

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">{label}</span>
      <CheckboxGroup
        name="roles"
        options={options}
        value={value}
        onChange={(next) => onChange(next as Role[])}
      />
      {showSuperAdmin && (
        <p className="text-xs text-on-surface-variant">
          Super Admin can&apos;t be combined with other roles — uncheck it to change the others.
        </p>
      )}
    </div>
  );
}
