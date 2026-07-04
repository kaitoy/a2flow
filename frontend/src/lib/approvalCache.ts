/** @module approvalCache — Dedupes and caches per-approval GET requests. */

import { type Approval, getApproval } from "@/lib/api";

const resolvedCache = new Map<string, Approval>();
const inFlight = new Map<string, Promise<Approval>>();

/**
 * Fetch an approval, reusing an in-flight request for the same id and skipping
 * the network entirely once the id is known to be resolved (approved/rejected
 * approvals are immutable, so there is no reason to ever refetch them).
 * Pending approvals are never cached long-term — only the in-flight promise is
 * deduped — since their status can still change while a viewer keeps the
 * bubble mounted.
 */
export function getApprovalCached(id: string): Promise<Approval> {
  const cached = resolvedCache.get(id);
  if (cached) return Promise.resolve(cached);

  let promise = inFlight.get(id);
  if (!promise) {
    promise = getApproval(id).finally(() => inFlight.delete(id));
    inFlight.set(id, promise);
  }
  return promise.then((approval) => {
    if (approval.status !== "pending") resolvedCache.set(id, approval);
    return approval;
  });
}

/** Test-only: clears cached/in-flight state so test cases stay isolated. */
export function __resetApprovalCacheForTests(): void {
  resolvedCache.clear();
  inFlight.clear();
}
