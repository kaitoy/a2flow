/**
 * @module TenantSettingsLayout — Gates `/tenant-settings` behind the `admin`
 * role (a `super_admin` passes, acting on the tenant selected in the tenant
 * switcher). Every other viewer gets an access-denied state and the page's data
 * fetch never fires. Mirrors `(admin)/system-settings/layout.tsx`.
 */
"use client";

import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Role, useHasRole } from "@/lib/roles";

export default function TenantSettingsLayout({ children }: { children: React.ReactNode }) {
  const isAdmin = useHasRole(Role.ADMIN);
  if (!isAdmin) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: "Tenant Settings" }]} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }
  return children;
}
