import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { SECRET_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewSecretPage from "./page";

describe("NewSecretPage", () => {
  it("renders name input, type toggle, and value input by default", () => {
    render(<NewSecretPage />);
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: /secret type/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/value/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/vault mount/i)).not.toBeInTheDocument();
  });

  it("switching to vault shows the reference inputs and hides the value", async () => {
    const user = userEvent.setup();
    render(<NewSecretPage />);
    await user.click(screen.getByRole("tab", { name: /hashicorp vault/i }));
    expect(screen.getByLabelText(/vault mount/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/vault path/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/vault key/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^value/i)).not.toBeInTheDocument();
  });

  it("submits a local secret with its value", async () => {
    const user = userEvent.setup();
    let receivedBody: unknown;
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", async ({ request }) => {
        receivedBody = await request.json();
        return envelope({ ...SECRET_1, id: "new-id" }, 201);
      })
    );

    render(<NewSecretPage />);
    await user.type(screen.getByLabelText(/name/i), "api-token");
    await user.type(screen.getByLabelText(/value/i), "tok-123");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({ name: "api-token", type: "local", value: "tok-123" })
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

    render(<NewSecretPage />);
    await user.type(screen.getByLabelText(/name/i), "vault-token");
    await user.click(screen.getByRole("tab", { name: /hashicorp vault/i }));
    await user.type(screen.getByLabelText(/vault mount/i), "secret");
    await user.type(screen.getByLabelText(/vault path/i), "myapp/github");
    await user.type(screen.getByLabelText(/vault key/i), "token");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "vault-token",
        type: "vault",
        vaultMount: "secret",
        vaultPath: "myapp/github",
        vaultKey: "token",
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

    render(<NewSecretPage />);
    await user.type(screen.getByLabelText(/name/i), "api-token");
    await user.type(screen.getByLabelText(/value/i), "tok-123");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/secrets"));
  });

  it("rejects submit when a local secret has no value", async () => {
    const user = userEvent.setup();
    const postSpy = vi.fn();
    server.use(
      http.post("http://localhost:8000/api/v1/secrets", () => {
        postSpy();
        return envelope({ ...SECRET_1, id: "new-id" }, 201);
      })
    );

    render(<NewSecretPage />);
    await user.type(screen.getByLabelText(/name/i), "api-token");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/value is required/i)).toBeInTheDocument());
    expect(postSpy).not.toHaveBeenCalled();
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(
        "http://localhost:8000/api/v1/secrets",
        () => new HttpResponse(null, { status: 422 })
      )
    );

    render(<NewSecretPage />);
    await user.type(screen.getByLabelText(/name/i), "api-token");
    await user.type(screen.getByLabelText(/value/i), "tok-123");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/422/)).toBeInTheDocument());
  });
});
