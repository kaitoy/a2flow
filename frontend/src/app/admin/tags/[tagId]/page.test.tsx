import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { ADMIN, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import TagDetailPage from "./page";

const BASE = "http://localhost:8000";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ tagId: "tag-1" }),
  useRouter: () => ({ push: (...args: unknown[]) => push(...args) }),
}));

describe("TagDetailPage", () => {
  it("titles the page with the saved name and fills the form", async () => {
    render(<TagDetailPage />, { preloadedState: ADMIN });
    expect(await screen.findByRole("heading", { name: "production" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Name/)).toHaveValue("production");
    expect(screen.getByLabelText(/Description/)).toHaveValue("Live customer-facing environment.");
  });

  it("submits the renamed tag", async () => {
    const user = userEvent.setup();
    let body: { name?: string } | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/tags/:tagId`, async ({ request }) => {
        body = (await request.json()) as { name?: string };
        return envelope({ id: "tag-1" });
      })
    );

    render(<TagDetailPage />, { preloadedState: ADMIN });
    const name = await screen.findByLabelText(/Name/);
    await user.clear(name);
    await user.type(name, "prod");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(body?.name).toBe("prod"));
  });

  it("keeps the loaded description in the submitted body when only the name changes", async () => {
    const user = userEvent.setup();
    let body: { name?: string; description?: string | null } | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/tags/:tagId`, async ({ request }) => {
        body = (await request.json()) as { name?: string; description?: string | null };
        return envelope({ id: "tag-1" });
      })
    );

    render(<TagDetailPage />, { preloadedState: ADMIN });
    const name = await screen.findByLabelText(/Name/);
    await user.clear(name);
    await user.type(name, "prod");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(body?.description).toBe("Live customer-facing environment."));
  });

  it("keeps the loaded color in the submitted body", async () => {
    const user = userEvent.setup();
    let body: { color?: string } | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/tags/:tagId`, async ({ request }) => {
        body = (await request.json()) as { color?: string };
        return envelope({ id: "tag-1" });
      })
    );

    render(<TagDetailPage />, { preloadedState: ADMIN });
    await screen.findByLabelText(/Name/);
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(body?.color).toBe("rose"));
  });

  it("warns that deleting detaches the tag everywhere", async () => {
    const user = userEvent.setup();
    render(<TagDetailPage />, { preloadedState: ADMIN });
    await screen.findByLabelText(/Name/);

    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(
      await screen.findByText(/removed from every record currently carrying it/)
    ).toBeInTheDocument();
  });

  it("renders read-only for a viewer who cannot write tags", async () => {
    render(<TagDetailPage />, { preloadedState: REQUESTER });
    await waitFor(() => expect(screen.getByRole("heading", { name: "production" })).toBeVisible());
    expect(screen.queryByLabelText(/Name/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.getByText("Live customer-facing environment.")).toBeInTheDocument();
  });

  it("shows the access-denied screen when the tag is forbidden", async () => {
    server.use(http.get(`${BASE}/api/v1/tags/:tagId`, () => envelopeErr("FORBIDDEN", "nope", 403)));
    render(<TagDetailPage />, { preloadedState: ADMIN });
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
  });
});
