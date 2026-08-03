/** @module AuditMeta — Read-only audit footer resolving created/updated user IDs to names. */
"use client";

import { useEffect, useState } from "react";
import { DateTime } from "@/components/ui/date-time";
import { DetailItem } from "@/components/ui/detail-list";
import { getUserNames } from "@/lib/api";

/** Props for {@link AuditMeta}: the audit fields shared by every persistent entity. */
export interface AuditMetaProps {
  /** ID of the user who created the record. */
  createdBy: string;
  /** ID of the user who last updated the record. */
  updatedBy: string;
  /** ISO timestamp the record was created, if available. */
  createdAt?: string;
  /** ISO timestamp the record was last updated, if available. */
  updatedAt?: string;
}

/**
 * Read-only footer showing who created and last updated a record (resolved to
 * "First Last", falling back to the raw ID) alongside the timestamps. Shared by
 * the admin detail pages so audit display is identical everywhere.
 *
 * Fixed at two columns (unlike `DetailList`'s responsive grid used elsewhere)
 * so "at"/"by" stay paired as a row. This component always renders inside
 * `FormLayout`'s fixed 16rem aside, which never reaches a container
 * breakpoint wide enough to earn two columns on its own.
 */
export function AuditMeta({ createdBy, updatedBy, createdAt, updatedAt }: AuditMetaProps) {
  const [names, setNames] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    let active = true;
    getUserNames([createdBy, updatedBy])
      .then((resolved) => {
        if (active) setNames(resolved);
      })
      .catch(() => {
        // Name resolution is best-effort; the raw ID is shown as a fallback.
      });
    return () => {
      active = false;
    };
  }, [createdBy, updatedBy]);

  const nameOf = (id: string) => names.get(id) ?? id;

  return (
    <dl className="grid grid-cols-2 gap-4 rounded-xl glass-panel p-4 text-on-surface-variant">
      {createdAt && <DetailItem label="Created at" value={<DateTime value={createdAt} />} />}
      <DetailItem label="Created by" value={nameOf(createdBy)} />
      {updatedAt && <DetailItem label="Updated at" value={<DateTime value={updatedAt} />} />}
      <DetailItem label="Updated by" value={nameOf(updatedBy)} />
    </dl>
  );
}
