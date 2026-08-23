/** @module useWorkflowExecutionNames — resolves workflow execution ids to display names for table cells. */
"use client";

import { useEffect, useState } from "react";
import { listWorkflowExecutions } from "@/lib/api";

/**
 * Resolve a set of workflow execution ids to their `name`, re-resolving
 * whenever the set of ids changes.
 *
 * The counterpart of {@link useGroupNames} for workflow executions: no
 * dedicated resolve endpoint exists, so this goes through the ordinary
 * `GET /workflow-executions` list with an `id:in:` filter. Best-effort in the
 * same way — a failed lookup leaves `names` at whatever it last held, so
 * callers falling back to the raw id degrade gracefully.
 *
 * @param ids - Workflow execution ids to resolve. May contain duplicates or falsy values.
 * @returns Map from execution id to its `name`, empty until the first resolution lands.
 */
export function useWorkflowExecutionNames(
  ids: Iterable<string | null | undefined>
): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());

  // Same keying trick as useGroupNames: depend on the set of ids being
  // resolved, not on the identity of the caller's array.
  const idsKey = [...new Set([...ids].filter((id): id is string => !!id))].sort().join(",");

  useEffect(() => {
    if (!idsKey) return;
    let active = true;
    const wanted = idsKey.split(",");
    listWorkflowExecutions({
      limit: wanted.length,
      filters: [{ field: "id", op: "in", value: idsKey }],
    })
      .then((executions) => {
        if (active) setNames(new Map(executions.map((e) => [e.id, e.name])));
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
