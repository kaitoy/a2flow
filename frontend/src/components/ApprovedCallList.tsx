/**
 * @module ApprovedCallList — renders the MCP calls an approval authorizes, so
 * the approver decides on the actual calls rather than on a description of them.
 */
"use client";

import { useEffect, useState } from "react";
import { useT } from "@/i18n/provider";
import type { Translator } from "@/i18n/translate";
import { type ApprovedCall, listMcpServers } from "@/lib/api";
import { Chip } from "./ui/chip";

/** One argument constraint, as stored: exactly one operator plus modifiers. */
type Constraint = Record<string, unknown>;

/** The operators a constraint may carry, in the order they are checked. */
const OPERATORS = ["eq", "in", "lte", "gte", "matches"] as const;

/**
 * Render one constraint as a phrase an approver can read.
 *
 * Deliberately not the stored JSON: the approver is being asked whether these
 * bounds are acceptable, and `{"lte": 2}` is a worse question than "at most 2".
 *
 * @param constraint - The stored constraint object.
 * @param t - The translator for the phrase; the bound values stay as JSON.
 * @returns The phrase, or the raw JSON when the operator is not one this build
 *   knows — a newer backend may declare an operator this page has not learned,
 *   and showing it verbatim is honest where showing nothing would not be.
 */
export function describeConstraint(constraint: Constraint, t: Translator): string {
  const operator = OPERATORS.find((candidate) => candidate in constraint);
  if (!operator) return JSON.stringify(constraint);
  const phrase = t(`approvals.constraint.${operator}`, {
    value: JSON.stringify(constraint[operator]),
  });
  return constraint.optional === true
    ? t("approvals.constraint.optional", { constraint: phrase })
    : phrase;
}

/** Props for {@link ApprovedCallList}. */
interface ApprovedCallListProps {
  /** The calls the approval authorizes. Renders nothing when empty. */
  calls: ApprovedCall[];
}

/**
 * List the calls an approval authorizes, each with its argument bounds.
 *
 * Shown while the request is pending — this is what the approver is deciding
 * on — and after it is settled, where it becomes the record of what was
 * approved. An approval carrying no declaration renders nothing at all: those
 * predate argument constraints, and an empty panel would imply the decision
 * bounded something when it did not.
 *
 * A call the workflow's design exempted from input approval says so in place of
 * its bounds. It is deliberately not left to render as a bare tool name, which
 * is what an entry bounding *no* input at all looks like — the two mean
 * opposite things, and the approver is agreeing to one of them.
 *
 * Each call is labelled with its MCP server's name, looked up here so every
 * place that shows an approval gets it. A server the viewer cannot see (or a
 * failed lookup) falls back to its id.
 */
export function ApprovedCallList({ calls }: ApprovedCallListProps) {
  const t = useT();
  const [serverNames, setServerNames] = useState<Map<string, string>>(new Map());
  const hasCalls = calls.length > 0;

  useEffect(() => {
    if (!hasCalls) return;
    let active = true;
    // The list (not a per-id GET) so a server hidden from the viewer is simply
    // absent instead of a 404 toast.
    listMcpServers({ limit: 1000 })
      .then((servers) => {
        if (active) setServerNames(new Map(servers.map((s) => [s.id, s.name])));
      })
      .catch(() => {
        // Non-fatal: the ids still identify the servers.
      });
    return () => {
      active = false;
    };
  }, [hasCalls]);

  if (!hasCalls) return null;

  return (
    <section className="mt-3">
      <h4 className="text-label-caps text-on-surface-variant">{t("app.thisAuthorizes")}</h4>
      <ul className="mt-2 flex flex-col gap-2">
        {calls.map((call) => {
          const args = Object.entries((call.arguments ?? {}) as Record<string, Constraint>);
          return (
            <li key={`${call.mcpServerId}/${call.toolName}`}>
              <Chip
                label={`${serverNames.get(call.mcpServerId) ?? call.mcpServerId}: ${call.toolName}`}
              />
              {call.unconstrainedArguments === true && (
                <p className="mt-1 ml-1 text-xs text-on-surface-variant">
                  {t("app.anyInputThisToolOnlyReadsSo")}
                </p>
              )}
              {args.length > 0 && (
                <dl className="mt-1 ml-1 flex flex-col gap-0.5">
                  {args.map(([name, constraint]) => (
                    <div key={name} className="flex gap-2 text-xs">
                      <dt className="font-mono text-on-surface">{name}</dt>
                      <dd className="text-on-surface-variant">
                        {describeConstraint(constraint, t)}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
