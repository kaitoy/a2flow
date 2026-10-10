"use client";

import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { FormField } from "@/components/admin/form-field";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  answerSessionElicitation,
  getSessionElicitation,
  isElicitationAlreadyAnsweredError,
  type McpElicitation,
  type McpElicitationAnswer,
} from "@/lib/api";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Radio } from "./ui/radio";
import { Select } from "./ui/select";

/**
 * The `activityType` the backend streams a server's question under (see
 * `infrastructure/mcp_elicitation.py`). Its content carries the ids this
 * component reads the question by.
 */
export const ELICITATION_ACTIVITY_TYPE = "mcp_elicitation";

/** How often an open question is re-read, to pick up an answer given elsewhere or its expiry. */
const REFRESH_MS = 5_000;

/** Choices at or below this count render as radios; more fall back to a select. */
const MAX_RADIO_OPTIONS = 4;

/** One primitive property of a question's form, as the MCP spec allows it. */
interface FieldSchema {
  type?: "string" | "number" | "integer" | "boolean";
  title?: string;
  description?: string;
  format?: string;
  default?: unknown;
  enum?: string[];
  enumNames?: string[];
  oneOf?: { const: string; title?: string }[];
}

/** One option of a single-select field. */
interface Choice {
  value: string;
  label: string;
}

/** What a question's state reads as once it is no longer open. */
type Outcome = "accepted" | "declined" | "cancelled" | "expired";

const OUTCOME_DISPLAY: Record<Outcome, { label: string; className: string }> = {
  accepted: { label: "Answered", className: "text-accent" },
  declined: { label: "Declined", className: "text-error" },
  cancelled: { label: "Dismissed", className: "text-on-surface-variant" },
  expired: { label: "Expired without an answer", className: "text-on-surface-variant" },
};

/** The options of a single-select field, or `null` for a free-form one. */
function choicesOf(field: FieldSchema): Choice[] | null {
  if (field.oneOf) return field.oneOf.map((o) => ({ value: o.const, label: o.title ?? o.const }));
  if (field.enum) {
    return field.enum.map((value, i) => ({ value, label: field.enumNames?.[i] ?? value }));
  }
  return null;
}

/** The HTML input type for a free-form string or number field. */
function inputTypeOf(field: FieldSchema): string {
  if (field.type === "number" || field.type === "integer") return "number";
  if (field.format === "email") return "email";
  if (field.format === "uri") return "url";
  if (field.format === "date") return "date";
  if (field.format === "date-time") return "datetime-local";
  return "text";
}

/** The form's starting values: each field's own default, if it declares one. */
function initialValues(properties: Record<string, FieldSchema>): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const [key, field] of Object.entries(properties)) {
    if (field.default !== undefined) values[key] = field.default;
    else if (field.type === "boolean") values[key] = false;
  }
  return values;
}

/** Turn the form's raw values into the content the server's schema expects. */
function toContent(
  properties: Record<string, FieldSchema>,
  values: Record<string, unknown>
): Record<string, unknown> {
  const content: Record<string, unknown> = {};
  for (const [key, field] of Object.entries(properties)) {
    const raw = values[key];
    if (raw === undefined || raw === "") continue;
    content[key] =
      field.type === "number" || field.type === "integer" ? Number(raw) : (raw as unknown);
  }
  return content;
}

/** Whether the question is open: pending, and not yet past its deadline. */
function isOpen(question: McpElicitation): boolean {
  if (question.status !== "pending") return false;
  return question.expiresAt == null || Date.parse(question.expiresAt) > Date.now();
}

/** What a closed question reads as. */
function outcomeOf(question: McpElicitation): Outcome {
  return question.status === "pending" ? "expired" : (question.status as Outcome);
}

/**
 * In-chat form for a question an MCP server asked in the middle of a tool call
 * (an MCP elicitation).
 *
 * The tool call -- and with it the agent's turn -- is waiting on the answer, so
 * the form is rendered from an `mcp_elicitation` activity that arrives while
 * the turn is still running, and answering it does not start a new turn: the
 * waiting call picks the answer up by itself.
 *
 * The form is built from the question's JSON schema, which MCP restricts to
 * flat primitive fields: text and number inputs, a checkbox for a boolean, and
 * radios -- or a select, past {@link MAX_RADIO_OPTIONS} -- for a single choice.
 * **Accept** submits the values; **Decline** refuses; **Cancel** dismisses the
 * question without choosing. The server decides what each means.
 *
 * Only the run's initiator may answer, the same rule as for the agent's own
 * forms, with no super-admin exception; everyone else sees the question and a
 * waiting note. The question is re-read every {@link REFRESH_MS} while open, so
 * an answer given in another tab, or the question's expiry, shows up here too.
 * `MCPElicitationService.answer` re-checks every rule server-side.
 */
export function ElicitationControls({
  executionId,
  sessionId,
  elicitationId,
  canAnswer,
}: {
  executionId: string;
  sessionId: string;
  elicitationId: string;
  /** Whether the signed-in viewer is the run's initiator. */
  canAnswer: boolean;
}) {
  const [question, setQuestion] = useState<McpElicitation | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<McpElicitationAnswer["action"] | null>(null);
  const action = useAsyncAction({ showDone: false });
  const fieldIdPrefix = useId();
  // Whether the form has been seeded with the schema's defaults; a refresh
  // must not wipe what the person has typed since.
  const seeded = useRef(false);

  const properties = (question?.requestedSchema?.properties ?? {}) as Record<string, FieldSchema>;
  const required = new Set((question?.requestedSchema?.required as string[] | undefined) ?? []);
  const open = question != null && isOpen(question);

  useEffect(() => {
    let active = true;
    const read = () =>
      getSessionElicitation(executionId, sessionId, elicitationId)
        .then((latest) => {
          if (!active) return;
          setQuestion(latest);
          if (!seeded.current) {
            seeded.current = true;
            setValues(
              initialValues(
                (latest.requestedSchema?.properties ?? {}) as Record<string, FieldSchema>
              )
            );
          }
        })
        .catch(() => {
          // Non-fatal: the next refresh tries again.
        });
    read();
    const timer = window.setInterval(read, REFRESH_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [executionId, sessionId, elicitationId]);

  const missingRequired = [...required].some((key) => {
    const value = values[key];
    return value === undefined || value === "";
  });

  const answer = async (choice: McpElicitationAnswer["action"]) => {
    if (action.inFlight || question == null || !isOpen(question)) return;
    setError(null);
    setPendingAction(choice);
    try {
      const body: McpElicitationAnswer =
        choice === "accept"
          ? { action: choice, content: toContent(properties, values) }
          : { action: choice };
      let answered: McpElicitation | null = null;
      await action.run(async () => {
        answered = await answerSessionElicitation(executionId, sessionId, elicitationId, body);
      });
      if (answered) setQuestion(answered);
    } catch (err) {
      if (isElicitationAlreadyAnsweredError(err)) {
        setError("This question was already answered, or has expired.");
        try {
          setQuestion(await getSessionElicitation(executionId, sessionId, elicitationId));
        } catch {
          // Non-fatal: the message above already explains what happened.
        }
        return;
      }
      console.error("failed to answer the MCP server's question", err);
      setError("Failed to send your answer. Please try again.");
    }
  };

  const setValue = (key: string, value: unknown) => setValues((v) => ({ ...v, [key]: value }));

  const renderField = (key: string, field: FieldSchema) => {
    const id = `${fieldIdPrefix}-${key}`;
    const label = field.title ?? key;
    const disabled = action.inFlight;
    const choices = choicesOf(field);
    if (field.type === "boolean") {
      return (
        <Checkbox
          key={key}
          label={label}
          checked={values[key] === true}
          disabled={disabled}
          onChange={(e) => setValue(key, e.target.checked)}
        />
      );
    }
    let control: ReactNode;
    if (choices && choices.length <= MAX_RADIO_OPTIONS) {
      control = (
        <div role="radiogroup" aria-labelledby={`${id}-label`} className="flex flex-wrap gap-1">
          {choices.map((choice) => (
            <Radio
              key={choice.value}
              name={id}
              label={choice.label}
              value={choice.value}
              checked={values[key] === choice.value}
              disabled={disabled}
              onChange={() => setValue(key, choice.value)}
            />
          ))}
        </div>
      );
    } else if (choices) {
      control = (
        <Select
          id={id}
          options={choices}
          value={typeof values[key] === "string" ? (values[key] as string) : ""}
          onChange={(value) => setValue(key, value)}
          disabled={disabled}
          placeholder="Choose…"
        />
      );
    } else {
      control = (
        <Input
          id={id}
          type={inputTypeOf(field)}
          step={field.type === "integer" ? 1 : undefined}
          value={values[key] === undefined ? "" : String(values[key])}
          disabled={disabled}
          onChange={(e) => setValue(key, e.target.value)}
        />
      );
    }
    return (
      <FormField key={key} htmlFor={id} label={label} required={required.has(key)}>
        {field.description && (
          <p className="text-xs text-on-surface-variant">{field.description}</p>
        )}
        {control}
      </FormField>
    );
  };

  return (
    <div className="glass-panel rounded-2xl p-4">
      <h3 className="text-sm font-semibold tracking-tight text-on-surface">
        {question ? `${question.serverName} asks for confirmation` : "Confirmation requested"}
      </h3>
      {question && (
        <>
          <p className="mt-1 text-xs text-on-surface-variant">
            Before running <code>{question.toolName}</code>
          </p>
          <p className="mt-2 whitespace-pre-line text-sm text-on-surface">{question.message}</p>
        </>
      )}

      {question &&
        (open ? (
          canAnswer ? (
            <>
              <div className="mt-3 flex flex-col gap-3">
                {Object.entries(properties).map(([key, field]) => renderField(key, field))}
              </div>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="primary"
                  disabled={action.inFlight || missingRequired}
                  status={pendingAction === "accept" ? action.status : "idle"}
                  pendingLabel="Sending…"
                  onClick={() => answer("accept")}
                >
                  Accept
                </Button>
                <Button
                  variant="secondary"
                  disabled={action.inFlight}
                  status={pendingAction === "decline" ? action.status : "idle"}
                  pendingLabel="Declining…"
                  onClick={() => answer("decline")}
                >
                  Decline
                </Button>
                <Button
                  variant="secondary"
                  disabled={action.inFlight}
                  status={pendingAction === "cancel" ? action.status : "idle"}
                  pendingLabel="Cancelling…"
                  onClick={() => answer("cancel")}
                >
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <p className="mt-3 text-sm text-on-surface-variant">
              Waiting for the initiator to respond.
            </p>
          )
        ) : (
          <p
            className={`mt-3 text-sm font-medium ${OUTCOME_DISPLAY[outcomeOf(question)].className}`}
          >
            {OUTCOME_DISPLAY[outcomeOf(question)].label}
          </p>
        ))}

      {error && <p className="mt-2 text-sm text-error">{error}</p>}
    </div>
  );
}
