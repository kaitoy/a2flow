import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store as appStore } from "@/store";
import { ADMIN, DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import TagsPage from "./page";

const BASE = "http://localhost:8000";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

function renderPage(state = ADMIN) {
  return render(<TagsPage />, { preloadedState: state });
}

describe("TagsPage", () => {
  it("shows loading state initially", () => {
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders a row per tag", async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByText("production").length).toBeGreaterThan(0));
    expect(screen.getAllByText("aws").length).toBeGreaterThan(0);
  });

  it("links each name to its detail page", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: "production" });
    expect(link).toHaveAttribute("href", "/admin/tags/tag-1");
  });

  it("hides the color name column by default", async () => {
    renderPage();
    await screen.findByRole("link", { name: "production" });
    expect(screen.queryByText("Rose")).not.toBeInTheDocument();
  });

  it("names the color once the column is shown", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("link", { name: "production" });

    await user.click(screen.getByRole("button", { name: "Columns" }));
    await user.click(await screen.findByRole("checkbox", { name: "Color" }));

    expect(await screen.findByText("Rose")).toBeInTheDocument();
  });

  it("offers the Add button to a developer", async () => {
    renderPage(DEVELOPER);
    await screen.findByRole("link", { name: "production" });
    expect(screen.getByRole("link", { name: "+ Add tag" })).toHaveAttribute(
      "href",
      "/admin/tags/new"
    );
  });

  it("hides the Add button and the row actions from a viewer who cannot write", async () => {
    renderPage(REQUESTER);
    await screen.findByRole("link", { name: "production" });
    expect(screen.queryByRole("link", { name: "+ Add tag" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
  });

  it("warns that deleting detaches the tag everywhere", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("link", { name: "production" });

    await user.click(screen.getAllByRole("button", { name: /Delete/ })[0]);

    expect(
      await screen.findByText(/removed from every record currently carrying it/)
    ).toBeInTheDocument();
  });

  it("shows the empty state when no tags exist", async () => {
    server.use(http.get(`${BASE}/api/v1/tags`, () => envelope([])));
    renderPage();
    expect(await screen.findByText("No tags created yet.")).toBeInTheDocument();
  });

  it("surfaces a load failure as a toast", async () => {
    server.use(http.get(`${BASE}/api/v1/tags`, () => envelopeErr("INTERNAL_ERROR", "boom", 500)));
    renderPage();
    await waitFor(() => expect(appStore.getState().toast.items.at(-1)?.message).toContain("boom"));
  });
});
