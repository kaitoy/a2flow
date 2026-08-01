import userEvent from "@testing-library/user-event";
import { delay, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import EditWorkflowPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1" });
});

describe("EditWorkflowPage", () => {
  it("loads the workflow into the form", async () => {
    render(<EditWorkflowPage />);
    await waitFor(() => expect(screen.getByLabelText(/^name/i)).toHaveValue("my-workflow"));
  });

  it("has no prompt field (workflows carry a plan, not a prompt)", async () => {
    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.queryByLabelText(/prompt/i)).not.toBeInTheDocument();
  });

  it("shows the workflow status", async () => {
    render(<EditWorkflowPage />);
    await waitFor(() => expect(screen.getByText("published")).toBeInTheDocument());
  });

  it("leaves the status bar unlit while nothing is generating", async () => {
    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.getByRole("region", { name: "Workflow status" })).not.toHaveClass("live-edge");
  });

  it("lights the status bar while the plan is still generating", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          status: "generating",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );

    render(<EditWorkflowPage />);
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Workflow status" })).toHaveClass("live-edge")
    );
  });

  it("lights the status bar while publish summarizes, then unlights it", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/publish", async () => {
        // Outlast useAsyncAction's 200ms pending gate so the light is reached.
        await delay(400);
        return envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: "Summarized",
          agentSkillId: "skill-1",
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        });
      })
    );

    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /publish/i }));

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Workflow status" })).toHaveClass("live-edge")
    );
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Workflow status" })).not.toHaveClass("live-edge")
    );
  });

  it("links the Agent Skill field to its detail page", async () => {
    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.getByRole("link", { name: "my-skill" })).toHaveAttribute(
      "href",
      "/admin/agent-skills/skill-1"
    );
  });

  it("links to the task template management page", async () => {
    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.getByRole("link", { name: /manage templates/i })).toHaveAttribute(
      "href",
      "/admin/workflows/wf-1/task-templates"
    );
  });

  it("publishes the workflow via the publish endpoint", async () => {
    const user = userEvent.setup();
    const publishSpy = vi.fn(() =>
      envelope({
        id: "wf-1",
        name: "my-workflow",
        description: "Summarized",
        agentSkillId: "skill-1",
        status: "published",
        generationError: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "",
        updatedBy: "",
      })
    );
    server.use(http.post("http://localhost:8000/api/v1/workflows/:id/publish", publishSpy));

    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /publish/i }));
    await waitFor(() => expect(publishSpy).toHaveBeenCalled());
  });

  it("shows an error toast when publish is rejected (no templates yet)", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/publish", () =>
        envelopeErr("WORKFLOW_NOT_RUNNABLE", "Workflow has no task templates", 409)
      )
    );

    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /publish/i }));
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Workflow has no task templates",
        variant: "error",
      })
    );
  });

  it("opens the workflow's planning session", async () => {
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

    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /open planning session/i }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/planning-sessions/ps-1"));
  });

  it("saves name and description only", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/workflows/:id", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({
          id: "wf-1",
          name: "Renamed",
          description: null,
          agentSkillId: "skill-1",
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        });
      })
    );

    render(<EditWorkflowPage />);
    const nameInput = await screen.findByLabelText(/^name/i);
    await waitFor(() => expect(nameInput).toHaveValue("my-workflow"));
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(receivedBody).toEqual({ name: "Renamed", description: null }));
  });

  it("offers no Discard changes action while the workflow is published", async () => {
    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.queryByRole("button", { name: /discard changes/i })).not.toBeInTheDocument();
  });

  it("discards a modified workflow's edits back to the published version", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          status: "modified",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        })
      )
    );
    const discardSpy = vi.fn(() =>
      envelope({
        id: "wf-1",
        tenantId: "tenant-1",
        name: "my-workflow",
        description: null,
        agentSkillId: "skill-1",
        status: "published",
        generationError: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "",
        updatedBy: "",
      })
    );
    server.use(http.post("http://localhost:8000/api/v1/workflows/:id/discard-changes", discardSpy));

    render(<EditWorkflowPage />);
    await waitFor(() => expect(screen.getByText("modified")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /discard changes/i }));
    await user.click(screen.getByRole("button", { name: /^discard$/i }));

    await waitFor(() => expect(discardSpy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("published")).toBeInTheDocument());
  });

  it("cancels back to the workflow list", async () => {
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

    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflows"));
  });
});
