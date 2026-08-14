import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { ADMIN, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { SECRET_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewSecretPage from "./page";

/** Render the form as an admin — the role creating a secret requires. */
function renderPage() {
  return render(<NewSecretPage />, { preloadedState: ADMIN });
}

/** Fill the first entry row, which the form starts with. */
async function typeEntry(user: ReturnType<typeof userEvent.setup>, key: string, value: string) {
  await user.type(screen.getByLabelText("entries key 1"), key);
  await user.type(screen.getByLabelText("entries value 1"), value);
}

describe("NewSecretPage", () => {
  it("renders name input, type toggle, and one entry row by default", () => {
    renderPage();
    expect(screen.getByLabelText(/^name/i)).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: /secret type/i })).toBeInTheDocument();
    expect(screen.getByLabelText("entries key 1")).toBeInTheDocument();
    expect(screen.getByLabelText("entries value 1")).toBeInTheDocument();
    expect(screen.queryByLabelText(/vault mount/i)).not.toBeInTheDocument();
  });

  it("masks entry values so they are not shoulder-readable", () => {
    renderPage();
    expect(screen.getByLabelText("entries value 1")).toHaveAttribute("type", "password");
  });

  it("switching to vault shows the reference inputs and hides the entries", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("tab", { name: /hashicorp vault/i }));
    expect(screen.getByLabelText(/vault mount/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/vault path/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/vault key/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("entries key 1")).not.toBeInTheDocument();
  });

  it("submits a local secret with its entries", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({ ...SECRET_1, id: "new-id" }, 201);
      })
    );

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "api-token");
    await typeEntry(user, "token", "tok-123");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "api-token",
        description: null,
        type: "local",
        entries: { token: "tok-123" },
      })
    );
  });

  it("submits every entry of a multi-entry secret", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({ ...SECRET_1, id: "new-id" }, 201);
      })
    );

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "aws-credentials");
    await typeEntry(user, "AWS_ACCESS_KEY_ID", "AKIA1");
    await user.click(screen.getByRole("button", { name: /add row/i }));
    await user.type(screen.getByLabelText("entries key 2"), "AWS_SECRET_ACCESS_KEY");
    await user.type(screen.getByLabelText("entries value 2"), "sk-1");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "aws-credentials",
        description: null,
        type: "local",
        entries: { AWS_ACCESS_KEY_ID: "AKIA1", AWS_SECRET_ACCESS_KEY: "sk-1" },
      })
    );
  });

  it("submits a vault secret with its reference", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({ ...SECRET_1, id: "new-id" }, 201);
      })
    );

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "vault-token");
    await user.click(screen.getByRole("tab", { name: /hashicorp vault/i }));
    await user.type(screen.getByLabelText(/vault mount/i), "secret");
    await user.type(screen.getByLabelText(/vault path/i), "myapp/github");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "vault-token",
        description: null,
        type: "vault",
        vaultMount: "secret",
        vaultPath: "myapp/github",
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
    await user.type(screen.getByLabelText(/^name/i), "api-token");
    await typeEntry(user, "token", "tok-123");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/secrets"));
  });

  it("rejects submit when a local secret has no entry", async () => {
    const user = userEvent.setup();
    const postSpy = vi.fn();
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", () => {
        postSpy();
        return envelope({ ...SECRET_1, id: "new-id" }, 201);
      })
    );

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "api-token");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(screen.getByText(/at least one entry is required/i)).toBeInTheDocument()
    );
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("rejects submit when an entry has no value", async () => {
    const user = userEvent.setup();
    const postSpy = vi.fn();
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", () => {
        postSpy();
        return envelope({ ...SECRET_1, id: "new-id" }, 201);
      })
    );

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "api-token");
    await user.type(screen.getByLabelText("entries key 1"), "token");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(screen.getByText(/every entry requires a value/i)).toBeInTheDocument()
    );
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", () =>
        envelopeErr("VALIDATION_ERROR", "Invalid request", 422)
      )
    );

    renderPage();
    await user.type(screen.getByLabelText(/^name/i), "api-token");
    await typeEntry(user, "token", "tok-123");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Invalid request",
        variant: "error",
      })
    );
  });

  it("refuses the form for a viewer without the admin role", () => {
    render(<NewSecretPage />, { preloadedState: REQUESTER });

    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });
});
