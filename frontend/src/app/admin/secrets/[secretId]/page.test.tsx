import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { SECRET_1, SECRET_VAULT_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import SecretDetailPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ secretId: "secret-1" });
}

describe("SecretDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the secret's name", async () => {
    setup();
    render(<SecretDetailPage />);
    expect(await screen.findByRole("heading", { name: "github-token" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("github-token")).toHaveAttribute("aria-current", "page");
  });

  it("prefills one blank-valued row per stored entry key", async () => {
    setup();
    render(<SecretDetailPage />);
    await waitFor(() => expect(screen.getByDisplayValue("github-token")).toBeInTheDocument());
    expect(screen.getByLabelText("entries key 1")).toHaveValue("token");
    expect(screen.getByLabelText("entries value 1")).toHaveValue("");
  });

  it("prefills the vault reference for a vault secret", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/secrets/:secretId", () => envelope(SECRET_VAULT_1))
    );
    render(<SecretDetailPage />);
    await waitFor(() => expect(screen.getByDisplayValue("vault-token")).toBeInTheDocument());
    expect(screen.getByDisplayValue("secret")).toBeInTheDocument();
    expect(screen.getByDisplayValue("myapp/github")).toBeInTheDocument();
    expect(screen.queryByLabelText(/vault key/i)).not.toBeInTheDocument();
  });

  it("sends the blank keep-existing sentinel when a value is untouched", async () => {
    setup();
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/secrets/:secretId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(SECRET_1);
      })
    );

    render(<SecretDetailPage />);
    await waitFor(() => screen.getByDisplayValue("github-token"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "github-token",
        type: "local",
        entries: { token: "" },
      })
    );
  });

  it("includes a retyped value in the patch", async () => {
    setup();
    let receivedBody: unknown;
    server.use(
      http.patch("http://localhost:8000/api/v1/secrets/:secretId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(SECRET_1);
      })
    );

    render(<SecretDetailPage />);
    await waitFor(() => screen.getByDisplayValue("github-token"));
    await userEvent.type(screen.getByLabelText("entries value 1"), "tok-456");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "github-token",
        type: "local",
        entries: { token: "tok-456" },
      })
    );
  });

  it("drops an entry from the patch when its row is removed", async () => {
    setup();
    let receivedBody: unknown;
    server.use(
      http.get("http://localhost:8000/api/v1/secrets/:secretId", () =>
        envelope({ ...SECRET_1, keys: ["token", "extra"] })
      ),
      http.patch("http://localhost:8000/api/v1/secrets/:secretId", async ({ request }) => {
        receivedBody = await request.json();
        return envelope(SECRET_1);
      })
    );

    render(<SecretDetailPage />);
    await waitFor(() => screen.getByDisplayValue("github-token"));
    await userEvent.click(screen.getByRole("button", { name: /remove entries row 2/i }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(receivedBody).toEqual({
        name: "github-token",
        type: "local",
        entries: { token: "" },
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

    render(<SecretDetailPage />);
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

    render(<SecretDetailPage />);
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

    render(<SecretDetailPage />);
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Secret not found",
        variant: "error",
      })
    );
  });
});
