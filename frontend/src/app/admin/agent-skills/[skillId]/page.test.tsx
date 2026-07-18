import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import EditAgentSkillPage from "./page";

const FULL_SKILL = {
  id: "skill-1",
  tenantId: "tenant-1",
  name: "my-skill",
  repoUrl: "https://github.com/example/repo",
  repoPath: "",
  description: null,
  syncStatus: "ready",
  syncError: null,
  commitSha: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
  syncedAt: "2026-01-01T00:00:00Z",
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
function authState(roles: Role[]): Partial<RootState> {
  return { auth: { user: { id: "u1", roles } as User, status: "authenticated" } };
}

/** Roles granting every agent-skill action (edit, delete, pull). */
const FULL_ACCESS = authState(["developer"]);
/** A signed-in user with no role granting agent-skill writes. */
const READ_ONLY = authState(["requester"]);

const SKILL_URL = "http://localhost:8000/api/v1/agent-skills/:skillId";

function setup() {
  vi.mocked(useParams).mockReturnValue({ skillId: "skill-1" });
}

describe("EditAgentSkillPage", () => {
  it("prefills form with skill data", async () => {
    setup();
    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => expect(screen.getByDisplayValue("my-skill")).toBeInTheDocument());
    expect(screen.getByDisplayValue("https://github.com/example/repo")).toBeInTheDocument();
  });

  it("submits update api on form submit", async () => {
    setup();
    const patchSpy = vi.fn(() => envelope(FULL_SKILL));
    server.use(http.patch("http://localhost:8000/api/v1/agent-skills/:skillId", patchSpy));

    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
  });

  it("prefills auth fields and sends null when cleared", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/agent-skills/:skillId", () =>
        envelope({ ...FULL_SKILL, repoAuthSecret: "git-token", repoAuthUsername: "oauth2" })
      )
    );
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/agent-skills/:skillId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(FULL_SKILL);
      })
    );

    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => expect(screen.getByDisplayValue("git-token")).toBeInTheDocument());
    expect(screen.getByDisplayValue("oauth2")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText(/auth secret/i));
    await userEvent.clear(screen.getByLabelText(/auth username/i));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "my-skill",
        repoUrl: "https://github.com/example/repo",
        repoPath: "",
        description: null,
        repoAuthSecret: null,
        repoAuthUsername: null,
      })
    );
  });

  it("navigates to list after save", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });

    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/agent-skills"));
  });

  it("calls delete api and navigates after confirm", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/agent-skills/:skillId", deleteSpy));

    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/agent-skills");
  });

  it("shows validation error on blur when required field is cleared", async () => {
    setup();
    const user = userEvent.setup();
    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    const nameInput = screen.getByLabelText(/^name/i);
    await user.clear(nameInput);
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get(
        "http://localhost:8000/api/v1/agent-skills/:skillId",
        () => new HttpResponse(null, { status: 404 })
      )
    );

    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => expect(screen.getByText(/404/)).toBeInTheDocument());
  });

  it("shows the sync status and short revision", async () => {
    setup();
    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    const panel = screen.getByRole("region", { name: /repository sync/i });
    expect(within(panel).getByText("ready")).toBeInTheDocument();
    expect(within(panel).getByText("a1b2c3d")).toBeInTheDocument();
  });

  it("surfaces the reason a failed clone gave", async () => {
    setup();
    server.use(
      http.get(SKILL_URL, () =>
        envelope({
          ...FULL_SKILL,
          syncStatus: "failed",
          syncError: "clone of https://github.com/example/repo failed: not found",
        })
      )
    );

    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    expect(screen.getByText(/clone of .* failed: not found/)).toBeInTheDocument();
    // The old revision is still published, so the skill still runs on it.
    expect(screen.getByText("a1b2c3d")).toBeInTheDocument();
  });

  it("calls the pull api", async () => {
    setup();
    const user = userEvent.setup();
    const pullSpy = vi.fn(() => envelope({ ...FULL_SKILL, syncStatus: "pending" }, 202));
    server.use(http.post(`${SKILL_URL}/pull`, pullSpy));

    render(<EditAgentSkillPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await user.click(screen.getByRole("button", { name: /pull/i }));

    await waitFor(() => expect(pullSpy).toHaveBeenCalled());
  });

  it("hides write actions from a user without the developer role", async () => {
    setup();
    render(<EditAgentSkillPage />, { preloadedState: READ_ONLY });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    expect(screen.queryByRole("button", { name: /pull/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    // The sync state is still readable — only the actions are gated.
    expect(screen.getByRole("region", { name: /repository sync/i })).toBeInTheDocument();
  });
});
