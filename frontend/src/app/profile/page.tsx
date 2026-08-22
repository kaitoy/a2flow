/** @module ProfilePage — The signed-in user's own profile: identity hero, read-only attributes, and the avatar editor. */
"use client";

import { useEffect, useState } from "react";
import { AvatarDialog } from "@/components/profile/AvatarDialog";
import { ProfileDetails } from "@/components/profile/ProfileDetails";
import { ProfileHero } from "@/components/profile/profile-hero";
import { Spinner } from "@/components/ui/spinner";
import { getUserGroupsForUser, type UserGroup } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";

/**
 * Profile page for the signed-in user: an identity hero naming them, then their
 * account and access attributes as two read-only cards.
 *
 * The backend only accepts self-service updates to `avatarConfig`, so everything
 * on the page proper is display-only — the one editable thing, the avatar, is
 * reached by clicking the hero's avatar, which opens {@link AvatarDialog}.
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
  const [avatarOpen, setAvatarOpen] = useState(false);

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
      <ProfileHero user={user} onEditAvatar={() => setAvatarOpen(true)} />
      <ProfileDetails user={user} groups={groups} />
      <AvatarDialog open={avatarOpen} onClose={() => setAvatarOpen(false)} user={user} />
    </div>
  );
}
