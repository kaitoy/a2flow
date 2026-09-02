import userEvent from "@testing-library/user-event";
import { delay, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { DEVELOPER, REQUESTER, SUPER_ADMIN } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import WorkflowDetailPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

/** Accessible name of the action opening the description diff dialog. */
const DIFF_BUTTON = "Show diff from the generated description";

/** Accessible name of the action re-summarizing the design conversation. */
const GENERATE_BUTTON = "Generate from the design conversation";

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1" });
});

describe("WorkflowDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the workflow's name", async () => {
    render(<WorkflowDetailPage />);
    expect(await screen.findByRole("heading", { name: "my-workflow" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("my-workflow")).toHaveAttribute("aria-current", "page");
  });

  it("loads the workflow into the form", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByLabelText(/^name/i)).toHaveValue("my-workflow"));
  });

  it("has no prompt field (workflows carry task templates, not a prompt)", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.queryByLabelText(/prompt/i)).not.toBeInTheDocument();
  });

  it("shows the workflow status", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByText("published")).toBeInTheDocument());
  });

  it("shows the workflow status to a requester too", async () => {
    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.getByText("published")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Workflow status" })).toBeInTheDocument();
  });

  it("leaves the status bar unlit while nothing is generating", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.getByRole("region", { name: "Workflow status" })).not.toHaveClass("live-edge");
  });

  it("lights the status bar while the task templates are still generating", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "generating",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Workflow status" })).toHaveClass("live-edge")
    );
  });

  it("lights the status bar while publishing, then unlights it", async () => {
    const user = userEvent.setup();
    server.use(
      // The Publish action is only offered while there is something to promote.
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "draft",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      ),
      http.post("http://localhost:8000/api/v1/workflows/:id/publish", async () => {
        // Outlast useAsyncAction's 200ms pending gate so the light is reached.
        await delay(400);
        return envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: "Summarized",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        });
      })
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /publish/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^publish$/i }));

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Workflow status" })).toHaveClass("live-edge")
    );
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Workflow status" })).not.toHaveClass("live-edge")
    );
  });

  it("links the Agent Skill field to its detail page", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.getByRole("link", { name: "my-skill" })).toHaveAttribute(
      "href",
      "/admin/agent-skills/skill-1"
    );
  });

  it("shows the skill's repo URL, ref, path, and pinned commit in a tooltip on hover", async () => {
    const user = userEvent.setup();
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));

    await user.hover(screen.getByRole("link", { name: "my-skill" }));

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Repo URL: https://github.com/example/repo");
    expect(tooltip).toHaveTextContent("Ref: default branch");
    expect(tooltip).toHaveTextContent("Path: repo root");
    // Pinned to the workflow's own agentSkillCommitSha ("a" x40), not the
    // skill's own commitSha, which differs in the mock data.
    expect(tooltip).toHaveTextContent("Commit: aaaaaaa");
  });

  it("navigates to the task template management page", async () => {
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

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /manage task templates/i }));
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/admin/workflows/wf-1/task-templates")
    );
  });

  it("lets a requester navigate to the read-only task template list via 'View task templates'", async () => {
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

    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(
      screen.queryByRole("button", { name: /manage task templates/i })
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /view task templates/i }));
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/admin/workflows/wf-1/task-templates")
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
        sessionId: "design-session-id",
        agentSkillCommitSha: "a".repeat(40),
        status: "published",
        generationError: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "user",
        updatedBy: "",
      })
    );
    server.use(
      // The Publish action is only offered while there is something to promote.
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "draft",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      ),
      http.post("http://localhost:8000/api/v1/workflows/:id/publish", publishSpy)
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /publish/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^publish$/i }));
    await waitFor(() => expect(publishSpy).toHaveBeenCalled());
  });

  it("shows an error toast when publish is rejected (no templates yet)", async () => {
    const user = userEvent.setup();
    server.use(
      // The Publish action is only offered while there is something to promote.
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "draft",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      ),
      http.post("http://localhost:8000/api/v1/workflows/:id/publish", () =>
        envelopeErr("WORKFLOW_NOT_RUNNABLE", "Workflow has no task templates", 409)
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /publish/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^publish$/i }));
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Workflow has no task templates",
        variant: "error",
      })
    );
  });

  it("opens the workflow's design session", async () => {
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

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /open design session/i }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/workflows/wf-1/design-session"));
  });

  it("hides the Run action from a viewer without the requester or developer role", async () => {
    render(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.queryByRole("button", { name: /run workflow/i })).not.toBeInTheDocument();
  });

  it("runs the workflow and navigates to the new session", async () => {
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

    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    await user.click(screen.getByRole("button", { name: /run workflow/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^run$/i }));
    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/workflow-executions/execution-1/session")
    );
  });

  it("shows an error toast when Run fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/execute", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    await user.click(screen.getByRole("button", { name: /run workflow/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^run$/i }));
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("disables Run for a requester on a draft workflow", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "draft",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.getByRole("button", { name: /run workflow/i })).toBeDisabled();
  });

  it("enables Run for a developer on a draft workflow, for pre-publish testing", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "draft",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByText("draft")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /run workflow/i })).not.toBeDisabled();
  });

  it("sends the tool mocks chosen in the Run dialog of a draft workflow", async () => {
    const user = userEvent.setup();
    let body: unknown;
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "draft",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      ),
      http.post("http://localhost:8000/api/v1/workflows/:id/execute", async ({ request }) => {
        body = await request.json();
        return envelope({ id: "execution-1" }, 201);
      })
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByText("draft")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /run workflow/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(
      await within(dialog).findByRole("checkbox", { name: /search returns nothing/ })
    );
    await user.click(within(dialog).getByRole("button", { name: /^run$/i }));

    await waitFor(() =>
      expect(body).toEqual({ toolMockIds: ["mock-1"], designSource: "published" })
    );
  });

  it("offers no tool mocks in the Run dialog of a published workflow", async () => {
    const user = userEvent.setup();
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await screen.findByRole("heading", { name: "my-workflow" });
    await user.click(screen.getByRole("button", { name: /run workflow/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByText("Mock tools")).not.toBeInTheDocument();
  });

  /**
   * Serve `wf-1` as `modified`. Only a developer can ever receive this status —
   * the backend reports the workflow as `published` to everyone else.
   */
  function mockModifiedWorkflow() {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "modified",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );
  }

  it("offers a developer the design choice on a modified workflow", async () => {
    mockModifiedWorkflow();
    const user = userEvent.setup();
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByText("modified")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /run workflow/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("radio", { name: /Published version/ })).toBeChecked();
  });

  it("runs the unpublished edits when the developer picks them", async () => {
    mockModifiedWorkflow();
    let body: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/execute", async ({ request }) => {
        body = await request.json();
        return envelope({ id: "execution-1" }, 201);
      })
    );
    const user = userEvent.setup();
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByText("modified")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /run workflow/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("radio", { name: /Unpublished edits/ }));
    await user.click(within(dialog).getByRole("button", { name: /^run$/i }));

    await waitFor(() => expect(body).toEqual({ toolMockIds: [], designSource: "live" }));
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
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        });
      })
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    const nameInput = await screen.findByLabelText(/^name/i);
    await waitFor(() => expect(nameInput).toHaveValue("my-workflow"));
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(receivedBody).toEqual({ name: "Renamed", description: null }));
  });

  it("returns to the workflow list after a successful save", async () => {
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

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    const nameInput = await screen.findByLabelText(/^name/i);
    await waitFor(() => expect(nameInput).toHaveValue("my-workflow"));
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflows"));
  });

  it("shows the generated description as read-only text for a non-super-admin", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: "AI summary of the design",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />);
    await waitFor(() => expect(screen.getByText("AI summary of the design")).toBeInTheDocument());
    // Anchored so the diff button — whose accessible name mentions the
    // generated description — isn't mistaken for the textarea.
    expect(screen.queryByLabelText(/^generated description$/i)).not.toBeInTheDocument();
  });

  it("lets a super admin edit the generated description", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: "AI summary of the design",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: SUPER_ADMIN });
    const field = await screen.findByLabelText(/^generated description$/i);
    await waitFor(() => expect(field).toHaveValue("AI summary of the design"));
  });

  it("includes generatedDescription in the save payload for a super admin", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: "AI summary",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      ),
      http.patch("http://localhost:8000/api/v1/workflows/:id", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({
          id: "wf-1",
          name: "my-workflow",
          description: null,
          generatedDescription: "Edited by admin",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        });
      })
    );

    render(<WorkflowDetailPage />, { preloadedState: SUPER_ADMIN });
    const field = await screen.findByLabelText(/^generated description$/i);
    await waitFor(() => expect(field).toHaveValue("AI summary"));
    await user.clear(field);
    await user.type(field, "Edited by admin");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "my-workflow",
        description: null,
        generatedDescription: "Edited by admin",
      })
    );
  });

  it("generates the description from the design conversation", async () => {
    const user = userEvent.setup();
    const generateSpy = vi.fn(() =>
      envelope({
        id: "wf-1",
        tenantId: "tenant-1",
        name: "my-workflow",
        description: null,
        generatedDescription: "A freshly generated summary",
        agentSkillId: "skill-1",
        sessionId: "design-session-id",
        agentSkillCommitSha: "a".repeat(40),
        status: "modified",
        generationError: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "user",
        updatedBy: "",
      })
    );
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/generate-description", generateSpy)
    );

    // Success toasts go through the component's own dispatch, so they land in
    // the render store rather than the global one api.ts reports errors to.
    const { store: renderStore } = render(<WorkflowDetailPage />, {
      preloadedState: DEVELOPER,
    });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: GENERATE_BUTTON }));

    await waitFor(() => expect(generateSpy).toHaveBeenCalled());
    // The developer sees the read-only rendering, so the fresh summary lands as
    // text rather than in a textarea.
    expect(await screen.findByText("A freshly generated summary")).toBeInTheDocument();
    expect(renderStore.getState().toast.items.at(-1)).toMatchObject({
      message: "Description generated",
    });
  });

  it("lights the generated-description field while a summary is generating, then unlights it", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/generate-description", async () => {
        // Outlast useAsyncAction's 200ms pending gate so the light is reached.
        await delay(400);
        return envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: "A freshly generated summary",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "modified",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        });
      })
    );

    render(<WorkflowDetailPage />, { preloadedState: SUPER_ADMIN });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: GENERATE_BUTTON }));

    await waitFor(() =>
      expect(screen.getByLabelText("Generated description").parentElement).toHaveClass("live-edge")
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Generated description").parentElement).not.toHaveClass(
        "live-edge"
      )
    );
  });

  it("shows an error toast when there is no design conversation to summarize", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/workflows/:id/generate-description", () =>
        envelopeErr(
          "WORKFLOW_DESCRIPTION_NOT_GENERATABLE",
          "Workflow has no design conversation to summarize",
          409
        )
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: GENERATE_BUTTON }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Workflow has no design conversation to summarize",
        variant: "error",
      })
    );
  });

  it("hides the generate action from a viewer who cannot edit workflows", async () => {
    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.queryByRole("button", { name: GENERATE_BUTTON })).not.toBeInTheDocument();
  });

  it("shows Name and Description as read-only text for a requester", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: "Collects the weekly report.",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await waitFor(() =>
      expect(screen.getByText("Collects the weekly report.")).toBeInTheDocument()
    );
    expect(screen.queryByLabelText(/^name/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^description/i)).not.toBeInTheDocument();
  });

  it("hides Save, Delete, and Open design session from a requester, but keeps templates viewable", async () => {
    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /open design session/i })).not.toBeInTheDocument();
    // Requesters can still reach the (read-only) task templates screen, just
    // under a label that doesn't imply edit rights.
    expect(
      screen.queryByRole("button", { name: /^manage task templates$/i })
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^view task templates$/i })).toBeInTheDocument();
    // With nothing to cancel, the navigate-back action reads "Back" instead.
    expect(screen.queryByRole("button", { name: /^cancel$/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^back$/i })).toBeInTheDocument();
  });

  it("hides Publish, Deactivate, and Discard changes from a requester regardless of status", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "modified",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.queryByRole("button", { name: /discard changes/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /deactivate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /publish/i })).not.toBeInTheDocument();
  });

  it("disables the generate action while the task templates are still generating", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "generating",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: GENERATE_BUTTON })).toBeDisabled()
    );
  });

  it("disables the task templates navigation button while the task templates are still generating", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "generating",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /manage task templates/i })).toBeDisabled()
    );
  });

  it("disables the diff action while there is no generated description to compare against", async () => {
    render(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.getByRole("button", { name: DIFF_BUTTON })).toBeDisabled();
  });

  it("diffs the description against the generated description", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: "Collects the weekly sales report.",
          generatedDescription: "Collects the monthly sales report.",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: "my-workflow" });
    await user.click(screen.getByRole("button", { name: DIFF_BUTTON }));

    const dialog = await screen.findByRole("dialog");
    expect(Array.from(dialog.querySelectorAll("del")).map((el) => el.textContent?.trim())).toEqual([
      "monthly",
    ]);
    expect(Array.from(dialog.querySelectorAll("ins")).map((el) => el.textContent?.trim())).toEqual([
      "weekly",
    ]);
  });

  it("diffs unsaved edits to the description", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          generatedDescription: "Runs monthly.",
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "published",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    const description = await screen.findByLabelText(/^description/i);
    await user.type(description, "Runs weekly.");
    await user.click(screen.getByRole("button", { name: DIFF_BUTTON }));

    const dialog = await screen.findByRole("dialog");
    expect(Array.from(dialog.querySelectorAll("ins")).map((el) => el.textContent?.trim())).toEqual([
      "weekly",
    ]);
  });

  it("offers no Discard changes action while the workflow is published", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.queryByRole("button", { name: /discard changes/i })).not.toBeInTheDocument();
  });

  it("hides the Publish action while the workflow is published", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.queryByRole("button", { name: /publish/i })).not.toBeInTheDocument();
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
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "modified",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
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
        sessionId: "design-session-id",
        agentSkillCommitSha: "a".repeat(40),
        status: "published",
        generationError: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "user",
        updatedBy: "",
      })
    );
    server.use(http.post("http://localhost:8000/api/v1/workflows/:id/discard-changes", discardSpy));

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
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

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /^cancel$/i }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflows"));
  });

  it("offers a Deactivate action while the workflow is published", async () => {
    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByLabelText(/^name/i));
    expect(screen.getByRole("button", { name: /deactivate/i })).toBeInTheDocument();
  });

  it("hides the Deactivate action once the workflow is draft", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelope({
          id: "wf-1",
          tenantId: "tenant-1",
          name: "my-workflow",
          description: null,
          agentSkillId: "skill-1",
          sessionId: "design-session-id",
          agentSkillCommitSha: "a".repeat(40),
          status: "draft",
          generationError: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "user",
          updatedBy: "",
        })
      )
    );

    render(<WorkflowDetailPage />);
    await screen.findByRole("heading", { name: "my-workflow" });
    expect(screen.queryByRole("button", { name: /deactivate/i })).not.toBeInTheDocument();
  });

  it("deactivates the workflow via the deactivate endpoint", async () => {
    const user = userEvent.setup();
    const deactivateSpy = vi.fn(() =>
      envelope({
        id: "wf-1",
        tenantId: "tenant-1",
        name: "my-workflow",
        description: null,
        agentSkillId: "skill-1",
        sessionId: "design-session-id",
        agentSkillCommitSha: "a".repeat(40),
        status: "draft",
        generationError: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
        createdBy: "user",
        updatedBy: "",
      })
    );
    server.use(http.post("http://localhost:8000/api/v1/workflows/:id/deactivate", deactivateSpy));

    render(<WorkflowDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByText("published")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /deactivate/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /^deactivate$/i }));

    await waitFor(() => expect(deactivateSpy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("draft")).toBeInTheDocument());
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id", () =>
        envelopeErr("FORBIDDEN", "Requires developer", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    render(<WorkflowDetailPage />);

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });
});
