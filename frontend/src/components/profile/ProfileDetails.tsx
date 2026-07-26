/** @module ProfileDetails — Read-only display of the signed-in user's own attributes. */
"use client";

import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { formatUserName, type User } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/roles";

/** Placeholder shown in place of an attribute that has no value. */
const EMPTY = "—";

/** Props for {@link ProfileDetails}. */
export interface ProfileDetailsProps {
  /** The signed-in user whose attributes are displayed. */
  user: User;
}

/**
 * Read-only card showing the signed-in user's own profile: the avatar and
 * display name, followed by the basic account attributes as a definition list.
 *
 * Nothing here is editable — the backend only lets a non-admin user update
 * their own `avatarConfig` (see `_SELF_SERVICE_FIELDS` in
 * `backend/services/user.py`), so every attribute below is rendered as plain
 * text rather than a disabled input. Avatar customization lives in its own
 * editable section on the same page.
 */
export function ProfileDetails({ user }: ProfileDetailsProps) {
  const fullName = formatUserName(user);
  const roles = user.roles ?? [];

  return (
    <div className="flex flex-col gap-6 rounded-2xl glass-panel-strong p-6">
      <div className="flex items-center gap-4">
        <Avatar user={user} size={96} />
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate font-display text-lg font-semibold tracking-tight text-on-surface">
            {fullName || user.username}
          </span>
          <span className="truncate font-mono text-sm text-on-surface-variant">
            @{user.username}
          </span>
        </div>
      </div>

      <DetailList className="border-t border-glass-border pt-6">
        <DetailItem label="Username" value={user.username} />
        <DetailItem label="Email" value={user.email} />
        <DetailItem label="First Name" value={user.firstName || EMPTY} />
        <DetailItem label="Last Name" value={user.lastName || EMPTY} />
        <DetailItem
          label="Roles"
          value={
            roles.length > 0 ? (
              <span className="flex flex-wrap gap-1.5">
                {roles.map((role) => (
                  <Badge key={role}>{ROLE_LABELS[role]}</Badge>
                ))}
              </span>
            ) : (
              EMPTY
            )
          }
        />
        <DetailItem label="Enabled" value={user.enabled ? "Yes" : "No"} />
        <DetailItem label="Email Verified" value={user.emailVerified ? "Yes" : "No"} />
      </DetailList>
    </div>
  );
}
