/**
 * @module mcp-tool-options — Encoding helpers for MCP tool bindings in WorkflowTask forms.
 *
 * The task-template forms edit tool bindings as a flat `string[]`, because
 * react-hook-form field arrays of scalars are far simpler to reset, diff, and
 * validate than arrays of objects. Each entry encodes a `(server, tool)` pair as
 * one composite string, and these helpers convert between that encoding and the
 * API's {@link ToolBinding} shape.
 */

import type { ToolBinding } from "@/lib/api";

/** Separator between the server id and the tool name inside a composite value. */
const SEPARATOR = "::";

/** How many characters of an unknown server's id stand in for its name. */
const ID_FALLBACK_LENGTH = 8;

/** Encode a tool binding as a composite option value (`<serverId>::<toolName>`). */
export function bindingToValue(binding: ToolBinding): string {
  return `${binding.mcpServerId}${SEPARATOR}${binding.toolName}`;
}

/** Decode a composite option value back into a tool binding. */
export function valueToBinding(value: string): ToolBinding {
  const index = value.indexOf(SEPARATOR);
  return {
    mcpServerId: value.slice(0, index),
    toolName: value.slice(index + SEPARATOR.length),
  };
}

/**
 * Build the API's binding list from the two arrays the forms hold.
 *
 * The forms keep the bound tools and the input-approval exemption as separate
 * `string[]`s — one is a multi-select, the other a checkbox group over the same
 * options — and this is where the two are folded back into one list. A tool
 * absent from `exempt` keeps the safe default: an approval covering its task
 * bounds the values it may be called with.
 *
 * @param values - Composite values of every bound tool.
 * @param exempt - Composite values of the tools whose input needs no approval.
 * @returns The bindings to send.
 */
export function toBindings(values: string[], exempt: string[]): ToolBinding[] {
  const exemptSet = new Set(exempt);
  return values.map((value) => ({
    ...valueToBinding(value),
    requiresInputApproval: !exemptSet.has(value),
  }));
}

/**
 * The composite values of the bindings that need no input approval.
 *
 * The inverse of {@link toBindings}' second argument, used to seed the edit
 * form from what the API returned.
 *
 * @param bindings - The bindings as the API returned them.
 * @returns Composite values of the exempt ones, in the given order.
 */
export function exemptValues(bindings: ToolBinding[]): string[] {
  return bindings.filter((b) => b.requiresInputApproval === false).map(bindingToValue);
}

/**
 * Human-readable label for a binding: `"<serverName>: <toolName>"`.
 *
 * A binding stores only the server's id, so a label needs the registry to
 * resolve it. When that lookup has not landed yet — or the registry read
 * failed — a truncated id stands in rather than the label collapsing to the
 * bare tool name, which would make two servers' identically named tools
 * indistinguishable.
 *
 * @param binding - The binding to describe.
 * @param serverNames - Registered server names by id.
 * @returns The chip label.
 */
export function bindingLabel(binding: ToolBinding, serverNames: Map<string, string>): string {
  const server =
    serverNames.get(binding.mcpServerId) ?? `${binding.mcpServerId.slice(0, ID_FALLBACK_LENGTH)}…`;
  return `${server}: ${binding.toolName}`;
}
