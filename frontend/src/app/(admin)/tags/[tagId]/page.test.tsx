import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { ADMIN, DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { TAG_1 } from "@/test/msw/handlers";
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

  it("loads the access-control flag and submits it untouched", async () => {
    const user = userEvent.setup();
    let body: { accessControl?: boolean } | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/tags/:tagId`, async ({ request }) => {
        body = (await request.json()) as { accessControl?: boolean };
        return envelope({ id: "tag-1" });
      })
    );

    render(<TagDetailPage />, { preloadedState: ADMIN });
    expect(await screen.findByLabelText("Access control")).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(body?.accessControl).toBe(true));
  });

  it("submits the access-control flag cleared when unticked", async () => {
    const user = userEvent.setup();
    let body: { accessControl?: boolean } | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/tags/:tagId`, async ({ request }) => {
        body = (await request.json()) as { accessControl?: boolean };
        return envelope({ id: "tag-1" });
      })
    );

    render(<TagDetailPage />, { preloadedState: ADMIN });
    await user.click(await screen.findByLabelText("Access control"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(body?.accessControl).toBe(false));
  });

  it("renders fully read-only for a developer viewing an access-control tag", async () => {
    render(<TagDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() => expect(screen.getByRole("heading", { name: "production" })).toBeVisible());
    expect(screen.queryByLabelText(/Name/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("lets a developer edit a plain (non-access-control) tag", async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE}/api/v1/tags/:tagId`, () => envelope({ ...TAG_1, accessControl: false }))
    );

    render(<TagDetailPage />, { preloadedState: DEVELOPER });
    const name = await screen.findByLabelText(/Name/);
    await user.clear(name);
    await user.type(name, "renamed");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
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
    // The flag reads as a value, not a checkbox.
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
  });

  it("shows the access-denied screen when the tag is forbidden", async () => {
    server.use(http.get(`${BASE}/api/v1/tags/:tagId`, () => envelopeErr("FORBIDDEN", "nope", 403)));
    render(<TagDetailPage />, { preloadedState: ADMIN });
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
  });
});
