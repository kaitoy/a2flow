/**
 * @module TenantsLayout — Gates every `/admin/tenants` route behind the
 * `super_admin` role. Non-`super_admin` viewers see an access-denied state
 * instead of the list/detail/new pages, so their data fetches never fire —
 * mirroring `(chat)/layout.tsx`'s `ChatAccessGate`. `AuthProvider` is already
 * supplied by the parent `admin/layout.tsx`, so this layout doesn't need its
 * own.
 */
"use client";

import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Role, useHasRole } from "@/lib/roles";

export default function TenantsLayout({ children }: { children: React.ReactNode }) {
  const isSuperAdmin = useHasRole(Role.SUPER_ADMIN);
  if (!isSuperAdmin) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={[{ label: "Admin", href: "/admin" }, { label: "Tenants" }]} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }
  return children;
}
