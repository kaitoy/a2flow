import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewAgentSkillPage from "./page";

/** Render the form as a developer — the role creating an agent skill requires. */
function renderPage() {
  return render(<NewAgentSkillPage />, { preloadedState: DEVELOPER });
}

describe("NewAgentSkillPage", () => {
  it("renders name input", () => {
    renderPage();
    expect(screen.getByLabelText(/^name/i)).toBeInTheDocument();
  });

  it("renders repo url input", () => {
    renderPage();
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

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalled());
  });

  it("submits the picked secret reference and the auth username", async () => {
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

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    // github-token holds a single entry, so choosing it completes the reference.
    await user.click(screen.getByRole("button", { name: "Select secret…" }));
    await user.click(await screen.findByRole("radio", { name: "github-token" }));
    await user.click(screen.getByRole("button", { name: "Select" }));
    await user.type(screen.getByLabelText(/auth username/i), "oauth2");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "Test",
        repoUrl: "https://x.com",
        repoRef: null,
        description: null,
        repoAuthPassword: "github-token/token",
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

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "Test",
        repoUrl: "https://x.com",
        repoRef: null,
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

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/agent-skills"));
  });

  it("shows validation error on blur when required field is empty", async () => {
    const user = userEvent.setup();
    renderPage();
    const nameInput = screen.getByLabelText(/^name/i);
    await user.click(nameInput);
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when name has a non-printable character", async () => {
    const user = userEvent.setup();
    renderPage();
    // A no-break space (U+00A0) is non-printable and rejected; an ordinary
    // space would be accepted.
    await user.type(screen.getByLabelText(/^name/i), "bad\u00a0name");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when repo url is invalid", async () => {
    const user = userEvent.setup();
    renderPage();
    const repoUrlInput = screen.getByLabelText(/repo url/i);
    await user.type(repoUrlInput, "not-a-url");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows error toast on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/agent-skills", () =>
        envelopeErr("INVALID_SECRET", "Auth password is invalid for this repo", 422)
      )
    );

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "Test");
    await user.type(screen.getByLabelText(/repo url/i), "https://x.com");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Auth password is invalid for this repo",
        variant: "error",
      })
    );
  });

  it("refuses the form for a viewer without the developer role", () => {
    render(<NewAgentSkillPage />, { preloadedState: REQUESTER });

    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });
});
