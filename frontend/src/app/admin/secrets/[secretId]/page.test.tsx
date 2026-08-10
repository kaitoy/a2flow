import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { ADMIN, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { SECRET_1, SECRET_VAULT_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import SecretDetailPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ secretId: "secret-1" });
}

/** Render the page as an admin — the role every secret write requires. */
function renderPage() {
  return render(<SecretDetailPage />, { preloadedState: ADMIN });
}

/** Render the page as a requester, who may read a secret but never write one. */
function renderPageReadOnly() {
  return render(<SecretDetailPage />, { preloadedState: REQUESTER });
}

describe("SecretDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the secret's name", async () => {
    setup();
    renderPage();
    expect(await screen.findByRole("heading", { name: "github-token" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("github-token")).toHaveAttribute("aria-current", "page");
  });

  it("prefills one blank-valued row per stored entry key", async () => {
    setup();
    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue("github-token")).toBeInTheDocument());
    expect(screen.getByLabelText("entries key 1")).toHaveValue("token");
    expect(screen.getByLabelText("entries value 1")).toHaveValue("");
  });

  it("prefills the vault reference for a vault secret", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/secrets/:secretId", () => envelope(SECRET_VAULT_1))
    );
    renderPage();
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

    renderPage();
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

    renderPage();
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

    renderPage();
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

    renderPage();
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

    renderPage();
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

    renderPage();
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Secret not found",
        variant: "error",
      })
    );
  });

  it("shows the access-denied state and no toast on a FORBIDDEN load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/secrets/:secretId", () =>
        envelopeErr("FORBIDDEN", "Requires developer", 403)
      )
    );
    const beforeCount = store.getState().toast.items.length;

    renderPage();

    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });

  describe("without the admin role", () => {
    it("lists the entry keys as values, with no value column to type into", async () => {
      setup();
      renderPageReadOnly();

      expect(await screen.findByRole("heading", { name: "github-token" })).toBeInTheDocument();
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("entries value 1")).not.toBeInTheDocument();
      expect(screen.getByText("Local (encrypted)")).toBeInTheDocument();
      expect(screen.getByText("token")).toBeInTheDocument();
    });

    it("renders a vault secret's mount and path as values", async () => {
      setup();
      server.use(
        http.get("http://localhost:8000/api/v1/secrets/:secretId", () => envelope(SECRET_VAULT_1))
      );
      renderPageReadOnly();

      expect(await screen.findByRole("heading", { name: "vault-token" })).toBeInTheDocument();
      expect(screen.getByText("HashiCorp Vault")).toBeInTheDocument();
      expect(screen.getByText("secret")).toBeInTheDocument();
      expect(screen.getByText("myapp/github")).toBeInTheDocument();
    });

    it("hides Save and Delete and offers Back instead of Cancel", async () => {
      setup();
      renderPageReadOnly();

      expect(await screen.findByRole("heading", { name: "github-token" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /back/i })).toBeInTheDocument();
    });
  });
});
