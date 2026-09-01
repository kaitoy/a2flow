/** @module useWorkflowNames — resolves workflow ids to display names for table cells. */
"use client";

import { useEffect, useState } from "react";
import { listWorkflows } from "@/lib/api";

/**
 * Resolve a set of workflow ids to their `name`, re-resolving whenever the set
 * of ids changes.
 *
 * The counterpart of {@link useWorkflowExecutionNames} for the parent workflow a
 * run came from: no dedicated resolve endpoint exists, so this goes through the
 * ordinary `GET /workflows` list with an `id:in:` filter. Best-effort in the
 * same way — a failed lookup leaves `names` at whatever it last held, so callers
 * falling back to the raw id degrade gracefully.
 *
 * One gap is inherent to going through the list: a caller without the
 * `developer` role never sees workflows that are still in `draft` status, so
 * their names will not resolve here and the caller falls back to the raw id.
 * Once a workflow is published its status changes and its name resolves for
 * everyone, so this only affects runs of a workflow that was never published.
 *
 * @param ids - Workflow ids to resolve. May contain duplicates or falsy values.
 * @returns Map from workflow id to its `name`, empty until the first resolution lands.
 */
export function useWorkflowNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());

  // Same keying trick as useWorkflowExecutionNames: depend on the set of ids
  // being resolved, not on the identity of the caller's array.
  const idsKey = [...new Set([...ids].filter((id): id is string => !!id))].sort().join(",");

  useEffect(() => {
    if (!idsKey) return;
    let active = true;
    const wanted = idsKey.split(",");
    listWorkflows({
      limit: wanted.length,
      filters: [{ field: "id", op: "in", value: idsKey }],
    })
      .then((workflows) => {
        if (active) setNames(new Map(workflows.map((w) => [w.id, w.name])));
      })
      .catch(() => {
        // Name resolution is best-effort; callers fall back to the raw id.
      });
    return () => {
      active = false;
    };
  }, [idsKey]);

  return names;
}
