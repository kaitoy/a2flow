import userEvent from "@testing-library/user-event";
import { delay, http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { GenerateWorkflowDialog } from "@/components/admin/generate-workflow-dialog";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";

const GENERATE_URL = "http://localhost:8000/api/v1/agent-skills/:skillId/workflows";

const NEW_WORKFLOW = {
  id: "new-wf-id",
  tenantId: "tenant-1",
  name: "my-flow",
  description: null,
  agentSkillId: "skill-1",
  status: "generating",
  generationError: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

/** Render the dialog open, wired to skill-1 and prefilled with "my-skill". */
function renderOpen(onClose = vi.fn()) {
  render(
    <GenerateWorkflowDialog open skillId="skill-1" defaultName="my-skill" onClose={onClose} />
  );
  return onClose;
}

describe("GenerateWorkflowDialog", () => {
  it("renders nothing while closed", () => {
    render(
      <GenerateWorkflowDialog
        open={false}
        skillId="skill-1"
        defaultName="my-skill"
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("prefills the workflow name with the given default", () => {
    renderOpen();
    expect(screen.getByLabelText(/workflow name/i)).toHaveValue("my-skill");
    expect(screen.getByLabelText(/prompt/i)).toHaveValue("");
  });

  it("submits the generation api and navigates to the new workflow", async () => {
    const user = userEvent.setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });
    let receivedBody: unknown;
    server.use(
      http.post(GENERATE_URL, async ({ request }) => {
        receivedBody = await request.json();
        return envelope(NEW_WORKFLOW, 201);
      })
    );

    renderOpen();
    const nameInput = screen.getByLabelText(/workflow name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "my-flow");
    await user.type(screen.getByLabelText(/prompt/i), "Do the thing");
    await user.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() => expect(receivedBody).toEqual({ name: "my-flow", prompt: "Do the thing" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflows/new-wf-id"));
  });

  it("lights the dialog edge while the generation request is in flight", async () => {
    const user = userEvent.setup();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });
    server.use(
      http.post(GENERATE_URL, async () => {
        // Outlast useAsyncAction's 200ms pending gate so the light is reached.
        await delay(400);
        return envelope(NEW_WORKFLOW, 201);
      })
    );

    renderOpen();
    expect(screen.getByRole("dialog")).not.toHaveClass("live-edge");
    await user.type(screen.getByLabelText(/prompt/i), "Do the thing");
    await user.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() => expect(screen.getByRole("dialog")).toHaveClass("live-edge"));
    await waitFor(() => expect(screen.getByRole("dialog")).not.toHaveClass("live-edge"));
  });

  it("rejects an empty prompt without calling the api", async () => {
    const user = userEvent.setup();
    const generateSpy = vi.fn(() => envelope(NEW_WORKFLOW, 201));
    server.use(http.post(GENERATE_URL, generateSpy));

    renderOpen();
    await user.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
    expect(generateSpy).not.toHaveBeenCalled();
  });

  it("surfaces a skill that has no published revision", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(GENERATE_URL, () =>
        envelopeErr("SKILL_NOT_READY", "Skill has no published revision", 409)
      )
    );

    renderOpen();
    await user.type(screen.getByLabelText(/prompt/i), "Do the thing");
    await user.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Skill has no published revision",
        variant: "error",
      })
    );
  });

  it("closes on Cancel and on Escape", async () => {
    const user = userEvent.setup();
    const onClose = renderOpen();
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();

    onClose.mockClear();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});
