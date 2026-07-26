/** @module ProfilePage — The signed-in user's own profile: read-only attributes plus avatar customization. */
"use client";

import { AvatarCustomizer } from "@/components/profile/AvatarCustomizer";
import { ProfileDetails } from "@/components/profile/ProfileDetails";
import { Spinner } from "@/components/ui/spinner";
import { useAppSelector } from "@/store/hooks";

/**
 * Profile page for the signed-in user. Shows their account attributes in a
 * read-only card — the backend only accepts self-service updates to
 * `avatarConfig` — followed by the editable avatar section.
 *
 * The surrounding `ProfileLayout` gates rendering on authentication, so the
 * user is normally present; a spinner covers the brief window before the auth
 * slice is populated.
 */
export default function ProfilePage() {
  const user = useAppSelector((s) => s.auth.user);

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
      <ProfileDetails user={user} />
      <AvatarCustomizer user={user} />
    </div>
  );
}
