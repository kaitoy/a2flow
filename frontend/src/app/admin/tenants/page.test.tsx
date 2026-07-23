import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import TenantsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("TenantsPage", () => {
  it("shows loading state initially", () => {
    render(<TenantsPage />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders tenant row after load", async () => {
    render(<TenantsPage />);
    await waitFor(() => expect(screen.getByText("Acme Corp")).toBeInTheDocument());
    expect(screen.getByText("acme-corp")).toBeInTheDocument();
  });

  it("name links to the edit page", async () => {
    render(<TenantsPage />);
    await waitFor(() => screen.getByText("Acme Corp"));
    expect(screen.getByRole("link", { name: "Acme Corp" })).toHaveAttribute(
      "href",
      "/admin/tenants/tenant-1"
    );
  });

  it("shows empty state when no tenants", async () => {
    server.use(http.get("http://localhost:8000/api/v1/tenants", () => envelope([])));
    render(<TenantsPage />);
    await waitFor(() => expect(screen.getByText("No tenants registered yet.")).toBeInTheDocument());
  });

  it("shows an error toast on api failure", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/tenants", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    render(<TenantsPage />);
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });

  it("add tenant link is present", async () => {
    render(<TenantsPage />);
    await waitFor(() => screen.getByText("Acme Corp"));
    expect(screen.getByRole("link", { name: /add tenant/i })).toHaveAttribute(
      "href",
      "/admin/tenants/new"
    );
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/tenants/:id", deleteSpy));

    render(<TenantsPage />);
    await waitFor(() => screen.getByText("Acme Corp"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  it("signals tenantsChanged on delete so pickers elsewhere refetch", async () => {
    const user = userEvent.setup();
    server.use(http.delete("http://localhost:8000/api/v1/tenants/:id", () => envelope(null)));

    const { store } = render(<TenantsPage />);
    await waitFor(() => screen.getByText("Acme Corp"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(store.getState().tenants.version).toBe(1));
  });
});
