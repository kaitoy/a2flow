/**
 * @module useNames — resolves record ids to display names for table cells.
 *
 * One mechanism behind every "show a name where the row only holds an id"
 * column: {@link useNames} keys its effect on the *set* of ids being resolved,
 * asks a resolver for that set once, and keeps whatever it last resolved when a
 * lookup fails, so callers fall back to the raw id instead of rendering nothing.
 * The exported hooks below pair it with the resolver for one kind of record.
 */
"use client";

import { useEffect, useState } from "react";
import {
  getUserNames,
  type ListQuery,
  listTenants,
  listUserGroups,
  listWorkflowExecutions,
  listWorkflows,
} from "@/lib/api";
import { Role, useHasRole } from "@/lib/roles";

/** Resolves a deduplicated, sorted set of ids to a map of id → display name. */
export type NameResolver = (ids: string[]) => Promise<Map<string, string>>;

/**
 * Resolve a set of ids to display names, re-resolving whenever the set changes.
 *
 * @param ids - Ids to resolve. May contain duplicates or falsy values, which are dropped.
 * @param resolve - The lookup for this kind of record.
 * @param enabled - When false, nothing is requested and the map stays empty.
 * @returns Map from id to display name, empty until the first resolution lands.
 */
export function useNames(
  ids: Iterable<string | null | undefined>,
  resolve: NameResolver,
  enabled = true
): Map<string, string> {
  const [names, setNames] = useState<Map<string, string>>(new Map());
  // A comma-joined key of the deduplicated, sorted ids lets the effect depend
  // on the set of ids actually being resolved, not on the identity of whatever
  // array/iterable the caller happened to construct this render.
  const idsKey = [...new Set([...ids].filter((id): id is string => !!id))].sort().join(",");

  useEffect(() => {
    if (!idsKey || !enabled) return;
    let active = true;
    resolve(idsKey.split(","))
      .then((resolved) => {
        if (active) setNames(resolved);
      })
      .catch(() => {
        // Name resolution is best-effort; callers fall back to the raw id.
      });
    return () => {
      active = false;
    };
  }, [idsKey, enabled, resolve]);

  return names;
}

/**
 * Build a resolver over an ordinary list endpoint, filtering by `id:in:`.
 *
 * Used where no dedicated resolve endpoint exists and the record is one any
 * authenticated caller may already read in full.
 *
 * @param list - The list call.
 * @param name - How to read a record's display name.
 * @returns A {@link NameResolver}.
 */
function byList<T extends { id: string }>(
  list: (query: ListQuery) => Promise<T[]>,
  name: (record: T) => string
): NameResolver {
  return async (ids) => {
    const records = await list({
      limit: ids.length,
      filters: [{ field: "id", op: "in", value: ids.join(",") }],
    });
    return new Map(records.map((record) => [record.id, name(record)]));
  };
}

const groupNames = byList(listUserGroups, (group) => group.name);
const workflowNames = byList(listWorkflows, (workflow) => workflow.name);
const executionNames = byList(listWorkflowExecutions, (execution) => execution.name);
const tenantNames = byList(listTenants, (tenant) => tenant.displayName);

/**
 * Resolve user ids to display names through `POST /users/resolve-names`, which
 * exists for users because another user's name can be invisible to the caller.
 *
 * @param ids - User ids, e.g. `rows.flatMap((r) => [r.createdBy, r.updatedBy])`.
 * @returns Map from user id to display name.
 */
export function useUserNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  return useNames(ids, getUserNames);
}

/**
 * Resolve user group ids to group names.
 *
 * @param ids - Group ids.
 * @returns Map from group id to group name.
 */
export function useGroupNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  return useNames(ids, groupNames);
}

/**
 * Resolve workflow ids to workflow names.
 *
 * @param ids - Workflow ids.
 * @returns Map from workflow id to workflow name.
 */
export function useWorkflowNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  return useNames(ids, workflowNames);
}

/**
 * Resolve workflow execution ids to their `name`.
 *
 * @param ids - Execution ids.
 * @returns Map from execution id to its name.
 */
export function useWorkflowExecutionNames(
  ids: Iterable<string | null | undefined>
): Map<string, string> {
  return useNames(ids, executionNames);
}

/**
 * Resolve tenant ids to their `displayName`.
 *
 * Tenant `displayName` is a `super_admin`-only datum: the backend restricts
 * `GET /tenants` to that role by design, and the resolved names only ever
 * surface in the cross-tenant "All tenants" view a `super_admin` opens. For any
 * other role the lookup would only earn a 403 (and a global error toast), so
 * the hook skips the request entirely and keeps returning an empty map.
 *
 * @param ids - Tenant ids.
 * @returns Map from tenant id to display name; always empty for a non-`super_admin`.
 */
export function useTenantNames(ids: Iterable<string | null | undefined>): Map<string, string> {
  return useNames(ids, tenantNames, useHasRole(Role.SUPER_ADMIN));
}
