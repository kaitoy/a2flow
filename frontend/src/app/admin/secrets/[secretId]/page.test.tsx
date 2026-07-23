import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { SECRET_1, SECRET_VAULT_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import EditSecretPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ secretId: "secret-1" });
}

describe("EditSecretPage", () => {
  it("prefills name and leaves the value blank for a local secret", async () => {
    setup();
    render(<EditSecretPage />);
    await waitFor(() => expect(screen.getByDisplayValue("github-token")).toBeInTheDocument());
    const valueInput = screen.getByLabelText(/value/i);
    expect(valueInput).toHaveValue("");
    expect(valueInput).toHaveAttribute("placeholder", "Leave blank to keep the current value");
  });

  it("prefills the vault reference for a vault secret", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/secrets/:secretId", () => envelope(SECRET_VAULT_1))
    );
    render(<EditSecretPage />);
    await waitFor(() => expect(screen.getByDisplayValue("vault-token")).toBeInTheDocument());
    expect(screen.getByDisplayValue("secret")).toBeInTheDocument();
    expect(screen.getByDisplayValue("myapp/github")).toBeInTheDocument();
    expect(screen.getByDisplayValue("token")).toBeInTheDocument();
  });

  it("omits the value from the patch when left blank", async () => {
    setup();
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/secrets/:secretId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(SECRET_1);
      })
    );

    render(<EditSecretPage />);
    await waitFor(() => screen.getByDisplayValue("github-token"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(receivedBody).toEqual({ name: "github-token", type: "local" }));
  });

  it("includes the value in the patch when entered", async () => {
    setup();
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/secrets/:secretId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(SECRET_1);
      })
    );

    render(<EditSecretPage />);
    await waitFor(() => screen.getByDisplayValue("github-token"));
    await userEvent.type(screen.getByLabelText(/value/i), "tok-456");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({ name: "github-token", type: "local", value: "tok-456" })
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

    render(<EditSecretPage />);
    await waitFor(() => screen.getByDisplayValue("github-token"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/secrets"));
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
    server.use(http.delete("http://localhost:8000/api/v1/secrets/:secretId", deleteSpy));

    render(<EditSecretPage />);
    await waitFor(() => screen.getByDisplayValue("github-token"));
    await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/secrets");
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/secrets/:secretId", () =>
        envelopeErr("NOT_FOUND", "Secret not found", 404)
      )
    );

    render(<EditSecretPage />);
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Secret not found",
        variant: "error",
      })
    );
  });
});
