import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
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

  it("shows an error when publish is rejected (no templates yet)", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(
        "http://localhost:8000/api/v1/workflows/:id/publish",
        () => new HttpResponse(null, { status: 409 })
      )
    );

    render(<EditWorkflowPage />);
    await waitFor(() => screen.getByLabelText(/^name/i));
    await user.click(screen.getByRole("button", { name: /publish/i }));
    await waitFor(() => expect(screen.getByText(/409/)).toBeInTheDocument());
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
});
