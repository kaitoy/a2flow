/** @module ChangePasswordLayout — Auth-gated shell for the forced password-change page. */
"use client";

import { AuthProvider } from "@/components/auth/auth-provider";

/**
 * Renders the page only once the session's user is known. No app chrome: a
 * user held here can use nothing else until the password is changed.
 *
 * @param props.children - The page content to render.
 */
export default function ChangePasswordLayout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
