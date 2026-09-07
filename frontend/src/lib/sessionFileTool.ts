/**
 * @module sessionFileTool — the chat's side of the agent's `write_session_file`
 * tool: the constants that identify it and the parser that turns its result into
 * the download card shown in the conversation.
 */

/**
 * Name of the backend tool the agent calls to attach a file it produced to the
 * session. Unlike `render_a2ui` and `render_approval` this runs on the server,
 * so the file only exists once the call's *result* comes back — which is why the
 * card is built from the result rather than from the call's arguments.
 */
export const WRITE_SESSION_FILE_TOOL_NAME = "write_session_file";

/**
 * Largest file the composer stages, mirroring the backend's default
 * `SESSION_FILE_MAX_BYTES` (20 MiB).
 *
 * A courtesy check only — it spares the user a doomed upload of a file the
 * server would refuse anyway. The server enforces its own configured limit and
 * remains authoritative, so a deployment that lowers it still rejects correctly,
 * just one round trip later.
 */
export const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;

/**
 * Activity-message type used to render a {@link SessionFileCard} from a
 * `write_session_file` result. Distinct from the generic tool-call type so the
 * message list can dispatch to the dedicated component, and so the call does not
 * also appear as a raw tool chip.
 */
export const SESSION_FILE_ACTIVITY_TYPE = "session_file";

/**
 * Content stored on a {@link SESSION_FILE_ACTIVITY_TYPE} activity message,
 * driving {@link SessionFileCard}.
 */
export interface SessionFileActivityContent {
  /** Id of the stored file, used to build its download URL. */
  fileId: string;
  /**
   * Id of the run the file belongs to. Carried in the tool result so the card is
   * self-contained: it can build its download link from the transcript alone,
   * including on a reload, without the surrounding chat passing it down.
   */
  workflowExecutionId: string;
  /**
   * Name the file was actually stored under. Not necessarily the name the agent
   * asked for: a name already taken in the session is stored as a numbered
   * variant rather than replacing what is there.
   */
  name: string;
  /** Size of the stored file in bytes. */
  sizeBytes: number;
}

/**
 * Read a `write_session_file` result into the content a download card needs.
 *
 * Returns `null` for anything that is not a successful write — a rejected file
 * comes back as `{error}`, and a truncated stream as a bare string — so the
 * caller renders nothing rather than a card pointing at no file.
 *
 * @param result - The parsed tool result.
 * @returns The card's content, or `null` when the result names no stored file.
 */
export function parseSessionFileResult(result: unknown): SessionFileActivityContent | null {
  if (result === null || typeof result !== "object") return null;
  const { fileId, workflowExecutionId, name, sizeBytes } = result as Record<string, unknown>;
  if (typeof fileId !== "string" || !fileId) return null;
  if (typeof workflowExecutionId !== "string" || !workflowExecutionId) return null;
  if (typeof name !== "string" || !name) return null;
  return {
    fileId,
    workflowExecutionId,
    name,
    sizeBytes: typeof sizeBytes === "number" ? sizeBytes : 0,
  };
}

/**
 * Render a byte count the way a file listing does — the largest unit that keeps
 * the number small, so a reader sees "12.4 KB" rather than "12678".
 *
 * @param bytes - The file's size in bytes.
 * @returns A short human-readable size.
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}
