import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import SecretsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("SecretsPage", () => {
  it("shows loading state initially", () => {
    render(<SecretsPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders local and vault rows after load", async () => {
    render(<SecretsPage />);
    await waitFor(() => expect(screen.getByText("github-token")).toBeInTheDocument());
    expect(screen.getByText("Local")).toBeInTheDocument();
    expect(screen.getByText("Encrypted value")).toBeInTheDocument();
    expect(screen.getByText("vault-token")).toBeInTheDocument();
    expect(screen.getByText("Vault")).toBeInTheDocument();
    expect(screen.getByText("secret/myapp/github · token")).toBeInTheDocument();
  });

  it("name links to the edit page", async () => {
    render(<SecretsPage />);
    await waitFor(() => screen.getByText("github-token"));
    expect(screen.getByRole("link", { name: "github-token" })).toHaveAttribute(
      "href",
      "/admin/secrets/secret-1"
    );
  });

  it("shows empty state when no secrets", async () => {
    server.use(http.get("http://localhost:8000/api/v1/secrets", () => envelope([])));
    render(<SecretsPage />);
    await waitFor(() => expect(screen.getByText("No secrets registered yet.")).toBeInTheDocument());
  });

  it("shows error banner on api failure", async () => {
    server.use(
      http.get(
        "http://localhost:8000/api/v1/secrets",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    render(<SecretsPage />);
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("add secret link is present", async () => {
    render(<SecretsPage />);
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

    render(<SecretsPage />);
    await waitFor(() => screen.getByText("github-token"));
    await user.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
