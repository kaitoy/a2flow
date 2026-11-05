/**
 * @module AuditLayout — Gates every `/audit` route behind the `admin`
 * role (a `super_admin` passes through {@link useHasRole}'s bypass). These lists
 * span every run, account, and message in the tenant, so they are not open to
 * the participants who can see their own records. Every other viewer gets an
 * access-denied state and the pages' data fetches never fire. Mirrors
 * `(admin)/system-settings/layout.tsx`; the parent `(admin)/layout.tsx` already
 * supplies `AuthProvider`.
 */
"use client";

import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { useT } from "@/i18n/provider";
import { Role, useHasRole } from "@/lib/roles";

export default function AuditLayout({ children }: { children: React.ReactNode }) {
  const t = useT();
  const isAdmin = useHasRole(Role.ADMIN);
  if (!isAdmin) {
    return (
      <AdminPageContainer>
        <Breadcrumbs
          items={[{ label: t("common.home"), href: "/" }, { label: t("common.auditLogs") }]}
        />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }
  return children;
}
