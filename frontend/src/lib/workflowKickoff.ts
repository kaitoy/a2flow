/** @module workflowKickoff — The fixed message that starts an execution run. */

/**
 * Auto-sent as the first chat message of a fresh WorkflowSession. The plan was
 * prepared and published in advance (the session's tasks are copies of the
 * workflow's templates), so this only tells the execution agent to begin; the
 * workflow's summarized description reaches it server-side as run context.
 */
export const EXECUTION_KICKOFF_PROMPT = "Start the workflow: execute the registered tasks.";
