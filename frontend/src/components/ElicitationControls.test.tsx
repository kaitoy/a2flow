import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { render, screen, waitFor } from "@/test/test-utils";
import { ElicitationControls } from "./ElicitationControls";

vi.mock("@/lib/api", () => ({
  getSessionElicitation: vi.fn(),
  answerSessionElicitation: vi.fn(),
  isElicitationAlreadyAnsweredError: vi.fn(),
}));

/** The question the Azure MCP Server asks before touching a secret. */
const AZURE_SCHEMA = {
  type: "object",
  properties: {
    decision: {
      type: "string",
      oneOf: [
        { const: "accept", title: "Approve" },
        { const: "reject", title: "Reject" },
      ],
    },
  },
  required: ["decision"],
};

/** A pending question with the given form, open for another five minutes. */
function question(overrides: Record<string, unknown> = {}) {
  return {
    id: "q1",
    serverName: "Azure MCP Server",
    toolName: "keyvault_secret_create",
    message: "Do you want to continue?",
    requestedSchema: AZURE_SCHEMA,
    status: "pending",
    expiresAt: new Date(Date.now() + 5 * 60_000).toISOString(),
    ...overrides,
  } as never;
}

function renderControls(canAnswer = true) {
  return render(
    <ElicitationControls executionId="e1" sessionId="s1" elicitationId="q1" canAnswer={canAnswer} />
  );
}

beforeEach(() => {
  vi.mocked(api.getSessionElicitation).mockReset();
  vi.mocked(api.answerSessionElicitation).mockReset();
  vi.mocked(api.isElicitationAlreadyAnsweredError).mockReturnValue(false);
  vi.mocked(api.getSessionElicitation).mockResolvedValue(question());
});

describe("ElicitationControls", () => {
  it("shows the server's question and which tool is waiting on it", async () => {
    renderControls();
    expect(await screen.findByText("Azure MCP Server asks for confirmation")).toBeInTheDocument();
    expect(screen.getByText("Do you want to continue?")).toBeInTheDocument();
    expect(screen.getByText("keyvault_secret_create")).toBeInTheDocument();
  });

  it("renders a titled choice as radios and accepts with the chosen value", async () => {
    vi.mocked(api.answerSessionElicitation).mockResolvedValue(
      question({ status: "accepted", content: { decision: "accept" } })
    );
    renderControls();

    const accept = await screen.findByRole("button", { name: "Accept" });
    expect(accept).toBeDisabled(); // the required choice is not made yet
    await userEvent.click(screen.getByRole("radio", { name: "Approve" }));
    await userEvent.click(accept);

    await waitFor(() =>
      expect(api.answerSessionElicitation).toHaveBeenCalledWith("e1", "s1", "q1", {
        action: "accept",
        content: { decision: "accept" },
      })
    );
    expect(await screen.findByText("Answered")).toBeInTheDocument();
  });

  it("declines without sending any values", async () => {
    vi.mocked(api.answerSessionElicitation).mockResolvedValue(question({ status: "declined" }));
    renderControls();

    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));

    await waitFor(() =>
      expect(api.answerSessionElicitation).toHaveBeenCalledWith("e1", "s1", "q1", {
        action: "decline",
      })
    );
    expect(await screen.findByText("Declined")).toBeInTheDocument();
  });

  it("sends numbers as numbers and booleans as booleans", async () => {
    vi.mocked(api.getSessionElicitation).mockResolvedValue(
      question({
        requestedSchema: {
          type: "object",
          properties: {
            replicas: { type: "integer", title: "Replicas" },
            force: { type: "boolean", title: "Force" },
          },
        },
      })
    );
    vi.mocked(api.answerSessionElicitation).mockResolvedValue(question({ status: "accepted" }));
    renderControls();

    await userEvent.type(await screen.findByLabelText("Replicas"), "3");
    await userEvent.click(screen.getByRole("checkbox", { name: "Force" }));
    await userEvent.click(screen.getByRole("button", { name: "Accept" }));

    await waitFor(() =>
      expect(api.answerSessionElicitation).toHaveBeenCalledWith("e1", "s1", "q1", {
        action: "accept",
        content: { replicas: 3, force: true },
      })
    );
  });

  it("shows only a waiting note to someone who is not the initiator", async () => {
    renderControls(false);

    expect(await screen.findByText("Waiting for the initiator to respond.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("shows an expired question as such, with no controls", async () => {
    vi.mocked(api.getSessionElicitation).mockResolvedValue(
      question({ expiresAt: new Date(Date.now() - 1000).toISOString() })
    );
    renderControls();

    expect(await screen.findByText("Expired without an answer")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
  });

  it("re-reads the question when it was already answered elsewhere", async () => {
    vi.mocked(api.answerSessionElicitation).mockRejectedValue(new Error("409"));
    vi.mocked(api.isElicitationAlreadyAnsweredError).mockReturnValue(true);
    renderControls();

    const decline = await screen.findByRole("button", { name: "Decline" });
    vi.mocked(api.getSessionElicitation).mockResolvedValue(question({ status: "accepted" }));
    await userEvent.click(decline);

    expect(
      await screen.findByText("This question was already answered, or has expired.")
    ).toBeInTheDocument();
    expect(await screen.findByText("Answered")).toBeInTheDocument();
  });
});
