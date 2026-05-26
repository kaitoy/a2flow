import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import EditAgentSkillPage from "./page";

const FULL_SKILL = {
  id: "skill-1",
  name: "My Skill",
  repoUrl: "https://github.com/example/repo",
  repoPath: "",
  description: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

function setup() {
  vi.mocked(useParams).mockReturnValue({ skillId: "skill-1" });
}

describe("EditAgentSkillPage", () => {
  it("prefills form with skill data", async () => {
    setup();
    render(<EditAgentSkillPage />);
    await waitFor(() => expect(screen.getByDisplayValue("My Skill")).toBeInTheDocument());
    expect(screen.getByDisplayValue("https://github.com/example/repo")).toBeInTheDocument();
  });

  it("submits update api on form submit", async () => {
    setup();
    const patchSpy = vi.fn(() => envelope(FULL_SKILL));
    server.use(http.patch("http://localhost:8000/api/v1/agent-skills/:skillId", patchSpy));

    render(<EditAgentSkillPage />);
    await waitFor(() => screen.getByDisplayValue("My Skill"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
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

    render(<EditAgentSkillPage />);
    await waitFor(() => screen.getByDisplayValue("My Skill"));
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

    render(<EditAgentSkillPage />);
    await waitFor(() => screen.getByDisplayValue("My Skill"));
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/agent-skills");
  });

  it("shows validation error on blur when required field is cleared", async () => {
    setup();
    const user = userEvent.setup();
    render(<EditAgentSkillPage />);
    await waitFor(() => screen.getByDisplayValue("My Skill"));
    const nameInput = screen.getByLabelText(/name/i);
    await user.clear(nameInput);
    await user.tab();
    await waitFor(() => expect(screen.getByText(/name is required/i)).toBeInTheDocument());
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get(
        "http://localhost:8000/api/v1/agent-skills/:skillId",
        () => new HttpResponse(null, { status: 404 })
      )
    );

    render(<EditAgentSkillPage />);
    await waitFor(() => expect(screen.getByText(/404/)).toBeInTheDocument());
  });
});
