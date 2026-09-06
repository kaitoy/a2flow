import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import AgentSkillDetailPage from "./page";

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

const SKILL_URL = "http://localhost:8000/api/v1/agent-skills/:skillId";

function setup() {
  vi.mocked(useParams).mockReturnValue({ skillId: "skill-1" });
}

describe("AgentSkillDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the skill's name", async () => {
    setup();
    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    expect(await screen.findByRole("heading", { name: "my-skill" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("my-skill")).toHaveAttribute("aria-current", "page");
  });

  it("prefills form with skill data", async () => {
    setup();
    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByDisplayValue("my-skill")).toBeInTheDocument());
    expect(screen.getByDisplayValue("https://github.com/example/repo")).toBeInTheDocument();
  });

  it("submits update api on form submit", async () => {
    setup();
    const patchSpy = vi.fn(() => envelope(FULL_SKILL));
    server.use(http.patch("http://localhost:8000/api/v1/agent-skills/:skillId", patchSpy));

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
  });

  it("prefills the secret picker and sends null when the reference is cleared", async () => {
    setup();
    server.use(
      http.get(SKILL_URL, () =>
        envelope({
          ...FULL_SKILL,
          repoAuthPassword: "github-token/token",
          repoAuthUsername: "oauth2",
        })
      )
    );
    let receivedBody: unknown;
    server.use(
      http.patch(SKILL_URL, async ({ request }) => {
        receivedBody = await request.json();
        return envelope(FULL_SKILL);
      })
    );

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    // The chip's remove button is what names the chosen secret uniquely.
    const chip = await screen.findByRole("button", { name: "Remove github-token" });
    expect(screen.getByRole("combobox", { name: "Entry Key" })).toHaveTextContent("token");
    expect(screen.getByDisplayValue("oauth2")).toBeInTheDocument();

    await userEvent.click(chip);
    await userEvent.clear(screen.getByLabelText(/auth username/i));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "my-skill",
        repoUrl: "https://github.com/example/repo",
        repoPath: "",
        repoRef: null,
        description: null,
        repoAuthPassword: null,
        repoAuthUsername: null,
      })
    );
  });

  it("keeps a reference whose secret was deleted, and saves it unchanged", async () => {
    setup();
    server.use(
      http.get(SKILL_URL, () => envelope({ ...FULL_SKILL, repoAuthPassword: "gone/pat" }))
    );
    let receivedBody: unknown;
    server.use(
      http.patch(SKILL_URL, async ({ request }) => {
        receivedBody = await request.json();
        return envelope(FULL_SKILL);
      })
    );

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    expect(await screen.findByText(/no secret named "gone" is registered/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(receivedBody).toMatchObject({ repoAuthPassword: "gone/pat" }));
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
      bfcacheId: "",
    });

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
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
      bfcacheId: "",
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/agent-skills/:skillId", deleteSpy));

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
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
    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    const nameInput = screen.getByLabelText(/^name/i);
    await user.clear(nameInput);
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("shows error toast on load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/agent-skills/:skillId", () =>
        envelopeErr("NOT_FOUND", "AgentSkill not found", 404)
      )
    );

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "AgentSkill not found",
        variant: "error",
      })
    );
  });

  it("shows the sync status and short revision", async () => {
    setup();
    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
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

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
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

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await user.click(screen.getByRole("button", { name: /pull/i }));

    await waitFor(() => expect(pullSpy).toHaveBeenCalled());
  });

  it("hides write actions from a user without the developer role", async () => {
    setup();
    render(<AgentSkillDetailPage />, { preloadedState: REQUESTER });
    expect(await screen.findByRole("heading", { name: "my-skill" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pull/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generate workflow/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /^workflow$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /back/i })).toBeInTheDocument();
    // The sync state is still readable — only the actions are gated.
    expect(screen.getByRole("region", { name: /repository sync/i })).toBeInTheDocument();
  });

  it("renders the fields as values for a user without the developer role", async () => {
    setup();
    server.use(
      http.get(SKILL_URL, () =>
        envelope({
          ...FULL_SKILL,
          repoRef: "main",
          description: "Reviews pull requests",
          repoAuthPassword: "github-token/token",
          repoAuthUsername: "oauth2",
        })
      )
    );

    render(<AgentSkillDetailPage />, { preloadedState: REQUESTER });

    expect(await screen.findByRole("heading", { name: "my-skill" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText("https://github.com/example/repo")).toBeInTheDocument();
    expect(screen.getByText("main")).toBeInTheDocument();
    expect(screen.getByText("Reviews pull requests")).toBeInTheDocument();
    expect(screen.getByText("oauth2")).toBeInTheDocument();
    // The stored reference is shown as-is rather than through the secret
    // picker, so no secret list is fetched for a viewer who cannot edit it.
    expect(screen.getByText("github-token/token")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("opens the generate dialog without asking when nothing was edited", async () => {
    setup();
    const user = userEvent.setup();
    const patchSpy = vi.fn(() => envelope(FULL_SKILL));
    server.use(http.patch(SKILL_URL, patchSpy));

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await user.click(screen.getByRole("button", { name: /generate workflow/i }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Generate Workflow")).toBeInTheDocument();
    // The workflow name is prefilled from the skill.
    expect(within(dialog).getByLabelText(/workflow name/i)).toHaveValue("my-skill");
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("disables generation while the skill has no published revision", async () => {
    setup();
    server.use(
      http.get(SKILL_URL, () => envelope({ ...FULL_SKILL, syncStatus: "pending", commitSha: null }))
    );

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    expect(screen.getByRole("button", { name: /generate workflow/i })).toBeDisabled();
  });

  it("offers to save unsaved edits before generating, then opens the dialog", async () => {
    setup();
    const user = userEvent.setup();
    const patchSpy = vi.fn(() => envelope({ ...FULL_SKILL, name: "renamed-skill" }));
    server.use(http.patch(SKILL_URL, patchSpy));

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    const nameInput = screen.getByDisplayValue("my-skill");
    await user.clear(nameInput);
    await user.type(nameInput, "renamed-skill");
    await user.click(screen.getByRole("button", { name: /generate workflow/i }));

    const confirm = await screen.findByRole("dialog");
    expect(within(confirm).getByText("Save changes?")).toBeInTheDocument();
    await user.click(within(confirm).getByRole("button", { name: /save and continue/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
    // The generate dialog takes over, seeded with the name that was just saved.
    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: /generate workflow/i })).toBeInTheDocument()
    );
    expect(screen.getByLabelText(/workflow name/i)).toHaveValue("renamed-skill");
  });

  it("aborts generation entirely when the save prompt is declined", async () => {
    setup();
    const user = userEvent.setup();
    const patchSpy = vi.fn(() => envelope(FULL_SKILL));
    server.use(http.patch(SKILL_URL, patchSpy));

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByDisplayValue("my-skill"));
    await user.type(screen.getByDisplayValue("my-skill"), "-edited");
    await user.click(screen.getByRole("button", { name: /generate workflow/i }));

    const confirm = await screen.findByRole("dialog");
    await user.click(within(confirm).getByRole("button", { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    setup();
    server.use(http.get(SKILL_URL, () => envelopeErr("FORBIDDEN", "Requires developer", 403)));
    const beforeCount = store.getState().toast.items.length;

    render(<AgentSkillDetailPage />, { preloadedState: DEVELOPER });

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });
});
