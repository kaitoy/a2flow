import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { ADMIN, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
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

/** Render the list as an admin — the role deletion requires. */
function renderPage(preloadedState = ADMIN) {
  return render(<WorkflowExecutionsPage />, { preloadedState });
}

describe("WorkflowExecutionsPage", () => {
  it("renders session row after load", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("My Workflow")).toBeInTheDocument());
  });

  it("links the Name cell to the session's detail page", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: "My Workflow" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1");
  });

  it("links the Agent Skill cell to the skill's detail page", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText("My Workflow"));

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Agent Skill" }));

    const link = await screen.findByRole("link", { name: "My Skill" });
    expect(link).toHaveAttribute("href", "/admin/agent-skills/skill-1");
  });

  it("resolves the workflow id to its name in the Workflow column and links to it", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/v1/workflows", () =>
        envelope([
          {
            id: "wf-1",
            name: "Invoice intake",
            tenantId: "tenant-1",
            description: null,
            generatedDescription: null,
            agentSkillId: "skill-1",
            sessionId: "design-session-id",
            agentSkillCommitSha: "a".repeat(40),
            status: "published",
            generationError: null,
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      )
    );
    renderPage();
    await waitFor(() => screen.getByText("My Workflow"));

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Workflow" }));

    const link = await screen.findByRole("link", { name: "Invoice intake" });
    expect(link).toHaveAttribute("href", "/admin/workflows/wf-1");
  });

  it("resolves the session user ID to the user's name", async () => {
    renderPage();
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

    renderPage();

    await waitFor(() => expect(screen.getByText("ANN")).toBeInTheDocument());
    expect(requests).toEqual([["ann", "bob", "cal"]]);
  });

  it("shows Name, Status, Initiator and Created At by default, but not Draft, Workflow, Agent Skill or Finished At", async () => {
    renderPage();
    await waitFor(() => screen.getByText("My Workflow"));
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Initiator" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Created At" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Workflow" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Agent Skill" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Finished At" })).not.toBeInTheDocument();
    expect(screen.getByText("completed")).toBeInTheDocument();
  });

  it("marks a draft run with a checkmark once the Draft column is shown", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions", () =>
        envelope(
          [
            { id: "run-real", name: "Real Run", isDraft: false },
            { id: "run-draft", name: "Draft Run", isDraft: true },
          ].map((r) => ({
            tenantId: "tenant-1",
            sessionId: `session-${r.id}`,
            workflowId: "wf-1",
            description: null,
            agentSkillId: "skill-1",
            agentSkillName: "My Skill",
            agentSkillRepoUrl: "https://github.com/example/repo",
            agentSkillRepoPath: "",
            initiatorId: "user",
            status: "completed",
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
            ...r,
          }))
        )
      )
    );
    renderPage();
    await screen.findByRole("link", { name: "Draft Run" });

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Draft" }));

    const draftRow = screen.getByRole("link", { name: "Draft Run" }).closest("tr");
    const realRow = screen.getByRole("link", { name: "Real Run" }).closest("tr");
    expect(within(draftRow as HTMLElement).getByText("✓")).toBeInTheDocument();
    expect(within(realRow as HTMLElement).queryByText("✓")).not.toBeInTheDocument();
  });

  it("filters the list by the Draft column", async () => {
    const user = userEvent.setup();
    const seen: string[] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/workflow-executions", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("q") ?? "");
        return envelope([]);
      })
    );
    renderPage();
    await waitFor(() => expect(seen.length).toBeGreaterThan(0));

    // Draft is an optional column now — turn it on before its header menu exists.
    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Draft" }));
    await user.click(screen.getByRole("button", { name: "Columns" }));

    await user.click(screen.getByRole("button", { name: "Draft" }));
    const select = await screen.findByRole("combobox");
    await user.click(select);
    await user.click(await screen.findByRole("option", { name: "No" }));

    await waitFor(() => expect(seen).toContain("isDraft:eq:false"));
  });

  it("links the user name to the user's edit page", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: "Alice Smith" });
    expect(link).toHaveAttribute("href", "/admin/users/user");
  });

  it("renders View tasks link to nested admin route", async () => {
    renderPage();
    await waitFor(() => screen.getByText("My Workflow"));
    const link = screen.getByRole("link", { name: "View tasks" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1/workflow-tasks");
  });

  it("renders Open workflow session link to the chat page", async () => {
    renderPage();
    await waitFor(() => screen.getByText("My Workflow"));
    const link = screen.getByRole("link", { name: "Open workflow session" });
    expect(link).toHaveAttribute("href", "/workflow-executions/execution-1/session");
  });

  it("shows empty-state message when no sessions exist", async () => {
    server.use(http.get("http://localhost:8000/api/v1/workflow-executions", () => envelope([])));
    renderPage();
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
    renderPage();
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

    renderPage();
    await waitFor(() => screen.getByText("My Workflow"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  it("hides the Delete button from a non-admin, but keeps the other row actions", async () => {
    renderPage(REQUESTER);
    await waitFor(() => screen.getByText("My Workflow"));
    expect(screen.getByRole("link", { name: "View tasks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open workflow session" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });
});
