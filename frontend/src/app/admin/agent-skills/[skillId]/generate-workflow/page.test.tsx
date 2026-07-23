import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import GenerateWorkflowPage from "./page";

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ skillId: "skill-1" });
});

describe("GenerateWorkflowPage", () => {
  it("prefills the workflow name with the skill name", async () => {
    render(<GenerateWorkflowPage />);
    // The global handlers serve AGENT_SKILL "my-skill" for GET /agent-skills/:id.
    await waitFor(() => expect(screen.getByLabelText(/workflow name/i)).not.toHaveValue(""));
  });

  it("renders the prompt textarea", () => {
    render(<GenerateWorkflowPage />);
    expect(screen.getByLabelText(/prompt/i)).toBeInTheDocument();
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
      http.post(
        "http://localhost:8000/api/v1/agent-skills/:skillId/workflows",
        async ({ request }) => {
          receivedBody = await request.json();
          return envelope(
            {
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
            },
            201
          );
        }
      )
    );

    render(<GenerateWorkflowPage />);
    const nameInput = screen.getByLabelText(/workflow name/i);
    await waitFor(() => expect(nameInput).not.toHaveValue(""));
    await user.clear(nameInput);
    await user.type(nameInput, "my-flow");
    await user.type(screen.getByLabelText(/prompt/i), "Do the thing");
    await user.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() => expect(receivedBody).toEqual({ name: "my-flow", prompt: "Do the thing" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflows/new-wf-id"));
  });

  it("shows an error toast when the skill has no published revision", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/agent-skills/:skillId/workflows", () =>
        envelopeErr("SKILL_NOT_READY", "Skill has no published revision", 409)
      )
    );

    render(<GenerateWorkflowPage />);
    const nameInput = screen.getByLabelText(/workflow name/i);
    await waitFor(() => expect(nameInput).not.toHaveValue(""));
    await user.type(screen.getByLabelText(/prompt/i), "Do the thing");
    await user.click(screen.getByRole("button", { name: /generate/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Skill has no published revision",
        variant: "error",
      })
    );
  });
});
