/** @module AuditMeta — Read-only audit footer resolving created/updated user IDs to names. */
"use client";

import { type ReactNode, useEffect, useState } from "react";
import { DateTime } from "@/components/ui/date-time";
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

/** Render a single labelled metadata cell. The value may be text or a node (e.g. a {@link DateTime}). */
function MetaItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs uppercase tracking-wide text-on-surface-variant">{label}</dt>
      <dd className="text-sm text-on-surface">{value}</dd>
    </div>
  );
}

/**
 * Read-only footer showing who created and last updated a record (resolved to
 * "First Last", falling back to the raw ID) alongside the timestamps. Shared by
 * the admin detail pages so audit display is identical everywhere.
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
    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 rounded-xl glass-panel p-4 text-on-surface-variant">
      <MetaItem label="Created by" value={nameOf(createdBy)} />
      <MetaItem label="Updated by" value={nameOf(updatedBy)} />
      {createdAt && <MetaItem label="Created at" value={<DateTime value={createdAt} />} />}
      {updatedAt && <MetaItem label="Updated at" value={<DateTime value={updatedAt} />} />}
    </dl>
  );
}
