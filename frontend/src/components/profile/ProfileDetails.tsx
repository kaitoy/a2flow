/**
 * @module ProfileDetails — Read-only display of the signed-in user's own
 * attributes, split into an account card and an access card.
 */
"use client";

import { ShieldCheck, UserRound } from "lucide-react";
import { InheritedRoles } from "@/components/admin/inherited-roles";
import { Badge } from "@/components/ui/badge";
import { Chip } from "@/components/ui/chip";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { SectionCard } from "@/components/ui/section-card";
import { Spinner } from "@/components/ui/spinner";
import { useT } from "@/i18n/provider";
import type { User, UserGroup } from "@/lib/api";
import { roleLabel } from "@/lib/roles";

/** Placeholder shown in place of an attribute that has no value. */
const EMPTY = "—";

/** Props for {@link ProfileDetails}. */
export interface ProfileDetailsProps {
  /** The signed-in user whose attributes are displayed. */
  user: User;
  /**
   * The tenant's groups the user belongs to. `null` while still loading —
   * rendered as a small spinner rather than a placeholder so an empty result
   * isn't shown prematurely.
   */
  groups: UserGroup[] | null;
}

/**
 * The signed-in user's own attributes, as two read-only {@link SectionCard}s:
 * **Account** (who the account belongs to) and **Access** (what it may do).
 *
 * Splitting them is what keeps the page scannable — a single nine-item list
 * gives the eye no place to stop, and the two halves answer genuinely different
 * questions. Identity itself (avatar, name, handle) and the `enabled` /
 * `emailVerified` flags live in
 * {@link import("./profile-hero").ProfileHero} above, so nothing is repeated
 * here.
 *
 * Nothing here is editable — the backend only lets a non-admin user update their
 * own `avatarConfig` and `language` (see `_SELF_SERVICE_FIELDS` in
 * `backend/services/user.py`), which have controls of their own, so every
 * attribute below is rendered as plain text rather than a disabled input.
 */
export function ProfileDetails({ user, groups }: ProfileDetailsProps) {
  const t = useT();
  const roles = user.roles ?? [];
  const groupRoles = user.groupRoles ?? [];

  return (
    <>
      <SectionCard icon={UserRound} title={t("profile.account")}>
        <DetailList>
          <DetailItem label={t("common.username")} value={user.username} />
          <DetailItem label={t("common.email")} value={user.email} />
          <DetailItem label={t("common.firstName")} value={user.firstName || EMPTY} />
          <DetailItem label={t("common.lastName")} value={user.lastName || EMPTY} />
        </DetailList>
      </SectionCard>

      <SectionCard icon={ShieldCheck} title={t("profile.access")}>
        {/* Every value here is a wrapping row of badges or chips, which a second
            column would only squeeze — so this list stays one column at any
            width. */}
        <DetailList singleColumn>
          <DetailItem
            label={t("common.roles")}
            value={
              roles.length > 0 ? (
                <span className="flex flex-wrap gap-1.5">
                  {roles.map((role) => (
                    <Badge key={role}>{roleLabel(role)}</Badge>
                  ))}
                </span>
              ) : (
                EMPTY
              )
            }
          />
          <DetailItem
            label={t("profile.rolesFromGroups")}
            value={groupRoles.length > 0 ? <InheritedRoles roles={groupRoles} /> : EMPTY}
          />
          <DetailItem
            label={t("common.groups")}
            value={
              groups === null ? (
                <Spinner size="sm" />
              ) : groups.length > 0 ? (
                <span className="flex flex-wrap gap-1.5">
                  {groups.map((group) => (
                    <Chip key={group.id} label={group.name} />
                  ))}
                </span>
              ) : (
                EMPTY
              )
            }
          />
        </DetailList>
      </SectionCard>
    </>
  );
}
