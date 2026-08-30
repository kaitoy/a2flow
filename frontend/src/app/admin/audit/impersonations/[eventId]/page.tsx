/** @module AuditImpersonationDetailPage — Read-only detail of one impersonation session. */
"use client";

import { VenetianMask } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { StatusCard } from "@/components/admin/status-card";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { DateTime } from "@/components/ui/date-time";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import { StatusDot } from "@/components/ui/status-dot";
import { useUserNames } from "@/hooks/useUserNames";
import {
  getImpersonationEvent,
  type ImpersonationEvent,
  isForbiddenError,
  SUPPRESS_FORBIDDEN_TOAST,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/**
 * Read-only detail of one impersonation session.
 *
 * There is no audit-meta aside here, unlike the other three audit detail pages:
 * this table carries none of the shared `createdBy`/`updatedBy` columns. The
 * actor and the instant are the record.
 */
export default function AuditImpersonationDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [event, setEvent] = useState<ImpersonationEvent | null>(null);

  useEffect(() => {
    let active = true;
    getImpersonationEvent(eventId, SUPPRESS_FORBIDDEN_TOAST)
      .then((e) => {
        if (active) setEvent(e);
      })
      .catch((err: unknown) => {
        if (!active) return;
        if (isForbiddenError(err)) setForbidden(true);
        // Any other failure is toasted globally by api.ts.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [eventId]);

  const names = useUserNames(event ? [event.impersonatorId, event.targetUserId] : []);

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Audit Logs", href: "/admin/audit" },
    { label: "Impersonations", href: "/admin/audit/impersonations" },
    { label: event ? (names.get(event.targetUserId) ?? event.targetUserId) : "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading || !event) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={VenetianMask} />}>
          <FormSkeleton fields={5} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  const userLink = (id: string) => (
    <Link href={`/admin/users/${id}`} className="text-accent transition-colors hover:underline">
      {names.get(id) ?? id}
    </Link>
  );

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout header={<AdminPageHeader title="Impersonation Session" icon={VenetianMask} />}>
        <StatusCard ariaLabel="Impersonation session state">
          {event.endedAt ? (
            <StatusDot dotClass="bg-on-surface-variant" label="Ended" />
          ) : (
            <StatusDot dotClass="bg-accent" label="Active" />
          )}
        </StatusCard>
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem label="Impersonator" value={userLink(event.impersonatorId)} />
            <DetailItem label="Target User" value={userLink(event.targetUserId)} />
            <DetailItem
              label="Target Tenant"
              value={
                event.targetTenantId ? (
                  <Link
                    href={`/admin/tenants/${event.targetTenantId}`}
                    className="text-accent transition-colors hover:underline"
                  >
                    {event.targetTenantId}
                  </Link>
                ) : (
                  EMPTY_VALUE
                )
              }
            />
            <DetailItem label="Started At" value={<DateTime value={event.startedAt} />} />
            <DetailItem
              label="Ended At"
              value={event.endedAt ? <DateTime value={event.endedAt} /> : EMPTY_VALUE}
            />
          </DetailList>
        </div>
      </FormLayout>
    </AdminPageContainer>
  );
}
