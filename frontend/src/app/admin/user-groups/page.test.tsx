import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { ADMIN, DEVELOPER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import UserGroupsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const BASE = "http://localhost:8000";

/** Render the list as an admin — the role every group write requires. */
function renderPage(preloadedState = ADMIN) {
  return render(<UserGroupsPage />, { preloadedState });
}

describe("UserGroupsPage", () => {
  it("shows loading state initially", () => {
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders a group row after load", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Developers")).toBeInTheDocument());
    expect(screen.getByText("People who build workflows")).toBeInTheDocument();
  });

  it("names the roles the group grants", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Developer")).toBeInTheDocument());
  });

  it("shows the member count", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Developers"));
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("carries the shared Tags column", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Developers"));
    expect(screen.getByRole("columnheader", { name: "Tags" })).toBeInTheDocument();
  });

  it("name links to the detail page", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Developers"));
    expect(screen.getByRole("link", { name: "Developers" })).toHaveAttribute(
      "href",
      "/admin/user-groups/group-1"
    );
  });

  it("shows empty state when no groups exist", async () => {
    server.use(http.get(`${BASE}/api/v1/user-groups`, () => envelope([])));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("No user groups created yet.")).toBeInTheDocument()
    );
  });

  it("shows an error toast on api failure", async () => {
    server.use(
      http.get(`${BASE}/api/v1/user-groups`, () =>
        envelopeErr("INTERNAL_ERROR", "Groups exploded", 500)
      )
    );
    renderPage();
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)).toMatchObject({
        message: "Groups exploded",
        variant: "error",
      })
    );
  });

  it("offers the Add button to an admin", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Developers"));
    expect(screen.getByRole("link", { name: "+ Add group" })).toBeInTheDocument();
  });

  it("hides the Add button and Actions column from a non-admin", async () => {
    renderPage(DEVELOPER);
    await waitFor(() => screen.getByText("Developers"));
    expect(screen.queryByRole("link", { name: "+ Add group" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
  });

  it("deletes a group after confirmation", async () => {
    let deleted = false;
    server.use(
      http.delete(`${BASE}/api/v1/user-groups/:groupId`, () => {
        deleted = true;
        return envelope(null);
      })
    );
    renderPage();
    await waitFor(() => screen.getByText("Developers"));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(deleted).toBe(true));
  });
});
