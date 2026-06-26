/** @module AccountPage — Self-service page for customizing the signed-in user's avatar. */
"use client";

import { AvatarCustomizer } from "@/components/account/AvatarCustomizer";
import { Spinner } from "@/components/ui/spinner";
import { useAppSelector } from "@/store/hooks";

/**
 * Account page where the signed-in user customizes their generated avatar.
 *
 * The surrounding {@link AccountLayout} gates rendering on authentication, so the
 * user is normally present; a spinner covers the brief window before the auth
 * slice is populated.
 */
export default function AccountPage() {
  const user = useAppSelector((s) => s.auth.user);

  if (!user) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return <AvatarCustomizer user={user} />;
}
