import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import NewAgentSkillPage from "./page";

describe("NewAgentSkillPage", () => {
  it("renders name input", () => {
    render(<NewAgentSkillPage />);
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  });

  it("renders repo url input", () => {
    render(<NewAgentSkillPage />);
    expect(screen.getByLabelText(/repo url/i)).toBeInTheDocument();
  });

  it("submits create api on form submit", async () => {
    const user = userEvent.setup();
    const createSpy = vi.fn(() =>
      envelope(
        {
          id: "new-id",
          name: "Test",
          repoUrl: "https://x.com",
          repoPath: "",
          description: null,
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        },
        201
      )
    );
    server.use(http.post("http://localhost:8000/agent-skills", createSpy));

    render(<NewAgentSkillPage />);
    await user.type(screen.getByLabelText(/name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalled());
  });

  it("navigates to list on success", async () => {
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

    render(<NewAgentSkillPage />);
    await user.type(screen.getByLabelText(/name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/agent-skills"));
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/agent-skills", () => new HttpResponse(null, { status: 422 }))
    );

    render(<NewAgentSkillPage />);
    await user.type(screen.getByLabelText(/name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/422/)).toBeInTheDocument());
  });
});
