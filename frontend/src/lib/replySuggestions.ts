/**
 * @module replySuggestions — the chat's side of the agent's `suggest_replies`
 * tool: the constant that identifies it and the parser that turns its arguments
 * into the reply chips shown under the chat input.
 */

/**
 * Name of the backend tool the agent calls, just before it stops to wait for the
 * user, to name a few replies the user is likely to give. Like
 * `write_session_file` it runs on the server, but unlike it the interesting
 * payload is the call's *arguments*, not its result — the tool itself only
 * acknowledges — so the chips are built from the arguments both live (the
 * streamed tool-call event) and on reload (the persisted assistant message).
 */
export const SUGGEST_REPLIES_TOOL_NAME = "suggest_replies";

/**
 * Most reply chips ever shown at once. The agent is asked for two to four; the
 * cap keeps a runaway list from turning the composer into a wall of pills.
 */
export const MAX_REPLY_SUGGESTIONS = 4;

/**
 * Read a `suggest_replies` call's arguments into the replies worth offering.
 *
 * The arguments are model output, so nothing about their shape is trusted:
 * anything that is not an array yields no chips, non-string, blank and repeated
 * entries are dropped, the rest are trimmed, and the list is cut at
 * {@link MAX_REPLY_SUGGESTIONS}.
 *
 * @param args - The parsed tool-call arguments.
 * @returns The replies to show, in the order the agent gave them.
 */
export function parseReplySuggestions(args: Record<string, unknown>): string[] {
  const raw = args.suggestions;
  if (!Array.isArray(raw)) return [];
  const replies: string[] = [];
  for (const entry of raw) {
    if (typeof entry !== "string") continue;
    const text = entry.trim();
    if (!text || replies.includes(text)) continue;
    replies.push(text);
    if (replies.length === MAX_REPLY_SUGGESTIONS) break;
  }
  return replies;
}
