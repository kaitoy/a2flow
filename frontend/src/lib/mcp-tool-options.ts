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
