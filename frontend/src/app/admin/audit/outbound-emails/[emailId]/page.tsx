/** @module AuditOutboundEmailDetailPage — Read-only detail of one queued notification email. */
"use client";

import { Mail } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminPageContainer } from "@/components/admin/admin-page-container";
import { AdminPageHeader } from "@/components/admin/admin-page-header";
import { AuditMeta } from "@/components/admin/audit-meta";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { FormLayout } from "@/components/admin/form-layout";
import { FormSkeleton } from "@/components/admin/form-skeleton";
import { StatusCard } from "@/components/admin/status-card";
import { AccessDeniedState } from "@/components/ui/access-denied-state";
import { Badge } from "@/components/ui/badge";
import { DateTime } from "@/components/ui/date-time";
import { DetailItem, DetailList } from "@/components/ui/detail-list";
import {
  getOutboundEmail,
  isForbiddenError,
  type OutboundEmail,
  SUPPRESS_FORBIDDEN_TOAST,
} from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/**
 * Read-only detail of one outgoing notification email.
 *
 * The body is shown in full here — the list truncates it into a cell. It is
 * frozen at the moment the notification was produced, not rendered at send time,
 * so what this page shows is the message as it was (or will be) delivered.
 */
export default function AuditOutboundEmailDetailPage() {
  const { emailId } = useParams<{ emailId: string }>();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [email, setEmail] = useState<OutboundEmail | null>(null);

  useEffect(() => {
    let active = true;
    getOutboundEmail(emailId, SUPPRESS_FORBIDDEN_TOAST)
      .then((e) => {
        if (active) setEmail(e);
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
  }, [emailId]);

  const breadcrumbItems = [
    { label: "Admin", href: "/admin" },
    { label: "Audit Logs", href: "/admin/audit" },
    { label: "Emails", href: "/admin/audit/outbound-emails" },
    { label: email?.subject || "…" },
  ];

  if (forbidden) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <AccessDeniedState fill="full" />
      </AdminPageContainer>
    );
  }

  if (loading || !email) {
    return (
      <AdminPageContainer>
        <Breadcrumbs items={breadcrumbItems} />
        <FormLayout header={<AdminPageHeader icon={Mail} />}>
          <FormSkeleton fields={7} />
        </FormLayout>
      </AdminPageContainer>
    );
  }

  return (
    <AdminPageContainer>
      <Breadcrumbs items={breadcrumbItems} />
      <FormLayout
        header={<AdminPageHeader title={email.subject} icon={Mail} />}
        aside={
          <AuditMeta
            createdBy={email.createdBy}
            updatedBy={email.updatedBy}
            createdAt={email.createdAt}
            updatedAt={email.updatedAt}
          />
        }
      >
        <StatusCard ariaLabel="Delivery status">
          <Badge>{email.status}</Badge>
        </StatusCard>
        <div className="flex flex-col gap-5 rounded-2xl glass-panel-strong p-6">
          <DetailList singleColumn>
            <DetailItem label="To" value={email.toEmail} />
            <DetailItem
              label="Body"
              value={<span className="whitespace-pre-wrap">{email.body}</span>}
            />
            <DetailItem label="Attempts" value={email.attempts} />
            <DetailItem label="Last Error" value={email.lastError || EMPTY_VALUE} />
            <DetailItem label="Next Attempt At" value={<DateTime value={email.nextAttemptAt} />} />
            <DetailItem
              label="Sent At"
              value={email.sentAt ? <DateTime value={email.sentAt} /> : EMPTY_VALUE}
            />
            <DetailItem
              label="Lease Expires At"
              value={email.leaseExpiresAt ? <DateTime value={email.leaseExpiresAt} /> : EMPTY_VALUE}
            />
            <DetailItem label="Notification" value={email.notificationId || EMPTY_VALUE} />
          </DetailList>
        </div>
      </FormLayout>
    </AdminPageContainer>
  );
}
