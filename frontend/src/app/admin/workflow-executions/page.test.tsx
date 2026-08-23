import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import WorkflowExecutionsPage from "./page";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("WorkflowExecutionsPage", () => {
  it("renders session row after load", async () => {
    render(<WorkflowExecutionsPage />);
    await waitFor(() => expect(screen.getByText("My Workflow")).toBeInTheDocument());
  });

  it("links the Name cell to the session's detail page", async () => {
    render(<WorkflowExecutionsPage />);
    const link = await screen.findByRole("link", { name: "My Workflow" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1");
  });

  it("links the Agent Skill cell to the skill's detail page", async () => {
    const user = userEvent.setup();
    render(<WorkflowExecutionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Agent Skill" }));

    const link = await screen.findByRole("link", { name: "My Skill" });
    expect(link).toHaveAttribute("href", "/admin/agent-skills/skill-1");
  });

  it("resolves the session user ID to the user's name", async () => {
    render(<WorkflowExecutionsPage />);
    await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());
  });

  it("resolves every row's initiator in a single request", async () => {
    const requests: string[][] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions", () =>
        envelope(
          ["ann", "bob", "cal"].map((initiatorId, i) => ({
            id: `execution-${i}`,
            tenantId: "tenant-1",
            sessionId: `session-${i}`,
            workflowId: "wf-1",
            name: `Workflow ${i}`,
            description: null,
            agentSkillId: "skill-1",
            agentSkillName: "My Skill",
            agentSkillRepoUrl: "https://github.com/example/repo",
            agentSkillRepoPath: "",
            initiatorId,
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          }))
        )
      ),
      http.post("http://localhost:8000/api/v1/users/resolve-names", async ({ request }) => {
        const { ids } = (await request.json()) as { ids: string[] };
        requests.push(ids);
        return envelope(ids.map((id) => ({ id, displayName: id.toUpperCase() })));
      })
    );

    render(<WorkflowExecutionsPage />);

    await waitFor(() => expect(screen.getByText("ANN")).toBeInTheDocument());
    expect(requests).toEqual([["ann", "bob", "cal"]]);
  });

  it("shows Name, Status, Initiator and Created At by default, but not Agent Skill or Finished At", async () => {
    render(<WorkflowExecutionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Initiator" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Created At" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Agent Skill" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Finished At" })).not.toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
  });

  it("links the user name to the user's edit page", async () => {
    render(<WorkflowExecutionsPage />);
    const link = await screen.findByRole("link", { name: "Alice Smith" });
    expect(link).toHaveAttribute("href", "/admin/users/user");
  });

  it("renders View tasks link to nested admin route", async () => {
    render(<WorkflowExecutionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    const link = screen.getByRole("link", { name: "View tasks" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1/workflow-tasks");
  });

  it("renders Open workflow session link to the chat page", async () => {
    render(<WorkflowExecutionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    const link = screen.getByRole("link", { name: "Open workflow session" });
    expect(link).toHaveAttribute("href", "/workflow-executions/execution-1/session");
  });

  it("shows empty-state message when no sessions exist", async () => {
    server.use(http.get("http://localhost:8000/api/v1/workflow-executions", () => envelope([])));
    render(<WorkflowExecutionsPage />);
    await waitFor(() =>
      expect(
        screen.getByText("No workflow executions yet. Run a workflow to create one.")
      ).toBeInTheDocument()
    );
  });

  it("shows an error toast when load fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    render(<WorkflowExecutionsPage />);
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/workflow-executions/:id", deleteSpy));

    render(<WorkflowExecutionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
