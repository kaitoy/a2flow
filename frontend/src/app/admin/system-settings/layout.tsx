/**
 * @module SystemSettingsLayout — Gates `/admin/system-settings` behind the
 * `super_admin` role. These settings are platform infrastructure, so there is no
 * tenant-admin carve-out: every other viewer gets an access-denied state and the
 * page's data fetch never fires. Mirrors `admin/tenants/layout.tsx`; the parent
 * `admin/layout.tsx` already supplies `AuthProvider`.
 */
"use client";

import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Role, useHasRole } from "@/lib/roles";

export default function SystemSettingsLayout({ children }: { children: React.ReactNode }) {
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  if (!isSuperAdmin) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "System Settings" }]} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }
  return children;
}
