/**
 * @module InheritedRoles — Read-only display of the roles a user gets from their groups.
 *
 * A user's effective roles are their direct grants unioned with the roles of
 * every group they belong to. Only the direct half is editable, so the two are
 * always shown apart: {@link RolesField} owns the editable half and this owns
 * the inherited one. Shared by the user detail page and the user list so both
 * render inherited roles the same muted way.
 */
"use client";

import { Chip } from "@/components/ui/chip";
import { ROLE_LABELS, type Role } from "@/lib/roles";

/** Props for {@link InheritedRoles}. */
export interface InheritedRolesProps {
  /** Roles the user inherits from their groups; renders nothing when empty. */
  roles: Role[];
}

/**
 * Render group-inherited roles as muted chips, visually distinct from the
 * directly granted roles so it is obvious which ones editing the user can
 * change.
 */
export function InheritedRoles({ roles }: InheritedRolesProps) {
  if (roles.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {roles.map((role) => (
        <Chip key={role} label={ROLE_LABELS[role]} />
      ))}
    </span>
  );
}

/**
 * The same chips under a labelled heading, for use inside a form column beneath
 * {@link RolesField}.
 */
export function InheritedRolesField({ roles }: InheritedRolesProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">Roles from groups</span>
      {roles.length === 0 ? (
        <p className="text-xs text-on-surface-variant">
          This user belongs to no group that grants a role.
        </p>
      ) : (
        <>
          <InheritedRoles roles={roles} />
          <p className="text-xs text-on-surface-variant">
            Granted by group membership. Edit the groups below, or the group itself, to change
            these.
          </p>
        </>
      )}
    </div>
  );
}
