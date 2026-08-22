/** @module ProfilePage — The signed-in user's own profile: read-only attributes plus avatar customization. */
"use client";

import { useEffect, useState } from "react";
import { AvatarCustomizer } from "@/components/profile/AvatarCustomizer";
import { ProfileDetails } from "@/components/profile/ProfileDetails";
import { Spinner } from "@/components/ui/spinner";
import { getUserGroupsForUser, type UserGroup } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";

/**
 * Profile page for the signed-in user. Shows their account attributes —
 * including their group memberships and the roles those groups grant — in a
 * read-only card, followed by the editable avatar section. The backend only
 * accepts self-service updates to `avatarConfig`, so everything above the
 * avatar section is display-only.
 *
 * The surrounding `ProfileLayout` gates rendering on authentication, so the
 * user is normally present; a spinner covers the brief window before the auth
 * slice is populated.
 */
export default function ProfilePage() {
  const user = useAppSelector((s) => s.auth.user);
  // Membership is not carried on the user record, so it is read through the
  // dedicated sub-resource, same as the admin user detail page. `null` means
  // still loading; a failure falls back to an empty list rather than blocking
  // the rest of the page.
  const [groups, setGroups] = useState<UserGroup[] | null>(null);

  useEffect(() => {
    if (!user) return;
    getUserGroupsForUser(user.id)
      .then(setGroups)
      .catch(() => setGroups([]));
  }, [user]);

  if (!user) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-4 sm:p-8">
      <h1 className="font-display text-3xl font-semibold tracking-tight text-gradient-accent">
        Profile
      </h1>
      <ProfileDetails user={user} groups={groups} />
      <AvatarCustomizer user={user} />
    </div>
  );
}
