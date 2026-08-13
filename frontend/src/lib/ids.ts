/** @module ids — helpers for comparing id selections held in component state. */

/**
 * Whether two id selections hold the same ids, ignoring order.
 *
 * Used by every form whose multi-select writes to a sub-resource (a user's
 * groups, a record's tags): those are separate requests, so they should only be
 * sent when the selection actually changed, and the pickers do not preserve a
 * stable order.
 *
 * @param a - One selection.
 * @param b - The other selection.
 * @returns True when both hold exactly the same ids.
 */
export function sameIds(a: string[], b: string[]): boolean {
  return a.length === b.length && [...a].sort().join() === [...b].sort().join();
}
