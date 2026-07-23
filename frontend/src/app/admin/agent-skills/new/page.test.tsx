import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewAgentSkillPage from "./page";

describe("NewAgentSkillPage", () => {
  it("renders name input", () => {
    render(<NewAgentSkillPage />);
    expect(screen.getByLabelText(/^name/i)).toBeInTheDocument();
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
    server.use(http.post("http://localhost:8000/api/v1/agent-skills", createSpy));

    render(<NewAgentSkillPage />);
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalled());
  });

  it("submits auth secret and username when provided", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/agent-skills", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(
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
        );
      })
    );

    render(<NewAgentSkillPage />);
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.type(screen.getByLabelText(/auth secret/i), "git-token");
    await user.type(screen.getByLabelText(/auth username/i), "oauth2");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "Test",
        repoUrl: "https://x.com",
        description: null,
        repoAuthSecret: "git-token",
        repoAuthUsername: "oauth2",
      })
    );
  });

  it("omits auth fields from the request when left blank", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/agent-skills", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(
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
        );
      })
    );

    render(<NewAgentSkillPage />);
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "Test",
        repoUrl: "https://x.com",
        description: null,
      })
    );
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
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/agent-skills"));
  });

  it("shows validation error on blur when required field is empty", async () => {
    const user = userEvent.setup();
    render(<NewAgentSkillPage />);
    const nameInput = screen.getByLabelText(/^name/i);
    await user.click(nameInput);
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when name has a non-printable character", async () => {
    const user = userEvent.setup();
    render(<NewAgentSkillPage />);
    // A no-break space (U+00A0) is non-printable and rejected; an ordinary
    // space would be accepted.
    await user.type(screen.getByLabelText(/^name/i), "bad\u00a0name");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when repo url is invalid", async () => {
    const user = userEvent.setup();
    render(<NewAgentSkillPage />);
    const repoUrlInput = screen.getByLabelText(/repo url/i);
    await user.type(repoUrlInput, "not-a-url");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows error toast on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/agent-skills", () =>
        envelopeErr("INVALID_SECRET", "Auth secret is invalid for this repo", 422)
      )
    );

    render(<NewAgentSkillPage />);
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Auth secret is invalid for this repo",
        variant: "error",
      })
    );
  });
});
