import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import AgentSkillsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
function authState(roles: Role[]): Partial<RootState> {
  return { auth: { user: { id: "u1", roles } as User, status: "authenticated" } };
}

/** Roles granting every agent-skill action (create, edit, delete, pull). */
const FULL_ACCESS = authState(["developer"]);
/** A signed-in user with no role granting agent-skill writes. */
const READ_ONLY = authState(["requester"]);

const SKILL_URL = "http://localhost:8000/api/v1/agent-skills";

describe("AgentSkillsPage", () => {
  it("shows loading state initially", () => {
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders skill row after load", async () => {
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => expect(screen.getByText("my-skill")).toBeInTheDocument());
  });

  it("name links to the edit page", async () => {
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-skill"));
    expect(screen.getByRole("link", { name: "my-skill" })).toHaveAttribute(
      "href",
      "/admin/agent-skills/skill-1"
    );
  });

  it("shows the sync status and the short revision", async () => {
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-skill"));
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("a1b2c3d")).toBeInTheDocument();
  });

  it("shows an em dash as the revision of a skill that has never published one", async () => {
    server.use(
      http.get(SKILL_URL, () =>
        envelope([
          {
            id: "skill-1",
            name: "my-skill",
            repoUrl: "https://github.com/example/repo",
            repoPath: "",
            description: null,
            syncStatus: "pending",
            syncError: null,
            commitSha: null,
            syncedAt: null,
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      )
    );
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-skill"));
    expect(screen.getByText("Cloning")).toBeInTheDocument();
  });

  it("shows empty state when no skills", async () => {
    server.use(http.get(SKILL_URL, () => envelope([])));
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() =>
      expect(screen.getByText("No agent skills registered yet.")).toBeInTheDocument()
    );
  });

  it("shows error banner on api failure", async () => {
    server.use(http.get(SKILL_URL, () => new HttpResponse(null, { status: 500 })));
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("add skill link is present", async () => {
    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-skill"));
    expect(screen.getByRole("link", { name: /add skill/i })).toHaveAttribute(
      "href",
      "/admin/agent-skills/new"
    );
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete(`${SKILL_URL}/:id`, deleteSpy));

    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-skill"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  it("calls the pull api", async () => {
    const user = userEvent.setup();
    const pullSpy = vi.fn(() => envelope({ id: "skill-1" }, 202));
    server.use(http.post(`${SKILL_URL}/:id/pull`, pullSpy));

    render(<AgentSkillsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-skill"));
    await user.click(screen.getByRole("button", { name: "Pull" }));
    await waitFor(() => expect(pullSpy).toHaveBeenCalled());
  });

  it("hides write actions from a user without the developer role", async () => {
    render(<AgentSkillsPage />, { preloadedState: READ_ONLY });
    await waitFor(() => screen.getByText("my-skill"));
    expect(screen.queryByRole("button", { name: "Pull" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /add skill/i })).not.toBeInTheDocument();
  });
});
