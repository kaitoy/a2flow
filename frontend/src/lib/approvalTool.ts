import type { Tool } from "@ag-ui/core";

/**
 * Name of the client-side (frontend) tool the workflow agent calls to show
 * approve/reject controls in the chat. Declared to the agent via
 * {@link RENDER_APPROVAL_TOOL} so it surfaces as a long-running client tool.
 */
export const RENDER_APPROVAL_TOOL_NAME = "render_approval";

/**
 * Activity-message type used to render an {@link ApprovalControls} surface from a
 * `render_approval` tool call. Distinct from the A2UI activity type so the
 * message list can dispatch to the dedicated approval component.
 */
export const APPROVAL_ACTIVITY_TYPE = "approval";

/**
 * Shape of the arguments the agent passes to the `render_approval` tool, also
 * stored as the activity message content that drives {@link ApprovalControls}.
 */
export interface ApprovalToolArgs {
  /** Id of the pending Approval record created by the `request_approval` backend tool. */
  approvalId: string;
  /** Short headline describing what needs approval. */
  title?: string;
  /** Longer explanation of the request. */
  description?: string;
}

/**
 * AG-UI frontend tool definition for rendering approve/reject controls. Passed
 * to `runAgent({ tools: [RENDER_APPROVAL_TOOL] })` so the agent can invoke it;
 * the call is handled on the client, which renders the controls and writes the
 * decision back via `PATCH /approvals/{id}`.
 */
export const RENDER_APPROVAL_TOOL: Tool = {
  name: RENDER_APPROVAL_TOOL_NAME,
  description:
    "Show approve/reject controls for a pending approval request previously created " +
    "with request_approval. Call this with the approval_id returned by request_approval " +
    "after explaining the request to the user. The user's decision is returned as the " +
    "result of this tool.",
  parameters: {
    type: "object",
    properties: {
      approvalId: {
        type: "string",
        description: "The approval_id returned by request_approval.",
      },
      title: {
        type: "string",
        description: "Short headline describing what needs approval.",
      },
      description: {
        type: "string",
        description: "Longer explanation of the request shown to the approver.",
      },
    },
    required: ["approvalId"],
  },
};
