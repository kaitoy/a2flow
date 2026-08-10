import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { ADMIN, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import SecretsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

/** Render the list as an admin — the role every secret write requires. */
function renderPage() {
  return render(<SecretsPage />, { preloadedState: ADMIN });
}

describe("SecretsPage", () => {
  it("shows loading state initially", () => {
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders local and vault rows after load", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("github-token")).toBeInTheDocument());
    expect(screen.getByText("Local")).toBeInTheDocument();
    expect(screen.getByText("vault-token")).toBeInTheDocument();
    expect(screen.getByText("Vault")).toBeInTheDocument();
  });

  it("hides the reference column by default", async () => {
    renderPage();
    await waitFor(() => screen.getByText("github-token"));
    expect(screen.queryByText("1 entry")).not.toBeInTheDocument();
    expect(screen.queryByText("secret/myapp/github")).not.toBeInTheDocument();
  });

  it("renders each secret's reference once the column is shown", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText("github-token"));

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Reference" }));

    expect(screen.getByText("1 entry")).toBeInTheDocument();
    expect(screen.getByText("secret/myapp/github")).toBeInTheDocument();
  });

  it("name links to the edit page", async () => {
    renderPage();
    await waitFor(() => screen.getByText("github-token"));
    expect(screen.getByRole("link", { name: "github-token" })).toHaveAttribute(
      "href",
      "/admin/secrets/secret-1"
    );
  });

  it("shows empty state when no secrets", async () => {
    server.use(http.get("http://localhost:8000/api/v1/secrets", () => envelope([])));
    renderPage();
    await waitFor(() => expect(screen.getByText("No secrets registered yet.")).toBeInTheDocument());
  });

  it("shows an error toast on api failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/secrets", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    renderPage();
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("add secret link is present", async () => {
    renderPage();
    await waitFor(() => screen.getByText("github-token"));
    expect(screen.getByRole("link", { name: /add secret/i })).toHaveAttribute(
      "href",
      "/admin/secrets/new"
    );
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/secrets/:id", deleteSpy));

    renderPage();
    await waitFor(() => screen.getByText("github-token"));
    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  describe("without the admin role", () => {
    it("hides the add link and the per-row delete", async () => {
      render(<SecretsPage />, { preloadedState: REQUESTER });
      await waitFor(() => screen.getByText("github-token"));

      expect(screen.queryByRole("link", { name: /add secret/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
      expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
      // The list itself stays readable — only the write actions are gated.
      expect(screen.getByRole("link", { name: "github-token" })).toBeInTheDocument();
    });
  });
});
