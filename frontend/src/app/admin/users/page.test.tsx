import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import UsersPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("UsersPage", () => {
  it("shows loading state initially", () => {
    render(<UsersPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders user row after load", async () => {
    render(<UsersPage />);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
  });

  it("username links to the edit page", async () => {
    render(<UsersPage />);
    await waitFor(() => screen.getByText("alice"));
    expect(screen.getByRole("link", { name: "alice" })).toHaveAttribute(
      "href",
      "/admin/users/user-1"
    );
  });

  it("shows empty state when no users", async () => {
    server.use(http.get("http://localhost:8000/api/v1/users", () => envelope([])));
    render(<UsersPage />);
    await waitFor(() => expect(screen.getByText("No users registered yet.")).toBeInTheDocument());
  });

  it("shows an error toast on api failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/users", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    render(<UsersPage />);
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("add user link is present", async () => {
    render(<UsersPage />);
    await waitFor(() => screen.getByText("alice"));
    expect(screen.getByRole("link", { name: /add user/i })).toHaveAttribute(
      "href",
      "/admin/users/new"
    );
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/users/:id", deleteSpy));

    render(<UsersPage />);
    await waitFor(() => screen.getByText("alice"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
