import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewTagPage from "./page";

const BASE = "http://localhost:8000";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: (...args: unknown[]) => push(...args) }),
}));

describe("NewTagPage", () => {
  it("submits the typed name with the default color", async () => {
    const user = userEvent.setup();
    let body: unknown;
    server.use(
      http.post(`${BASE}/api/v1/tags`, async ({ request }) => {
        body = await request.json();
        return envelope({ id: "new-tag-id" }, 201);
      })
    );

    render(<NewTagPage />, { preloadedState: DEVELOPER });
    await user.type(screen.getByLabelText(/Name/), "production");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(body).toEqual({ name: "production", color: "slate", description: null })
    );
  });

  it("submits the typed description", async () => {
    const user = userEvent.setup();
    let body: { description?: string | null } | undefined;
    server.use(
      http.post(`${BASE}/api/v1/tags`, async ({ request }) => {
        body = (await request.json()) as { description?: string | null };
        return envelope({ id: "new-tag-id" }, 201);
      })
    );

    render(<NewTagPage />, { preloadedState: DEVELOPER });
    await user.type(screen.getByLabelText(/Name/), "production");
    await user.type(screen.getByLabelText(/Description/), "Live customer-facing environment.");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(body?.description).toBe("Live customer-facing environment."));
  });

  it("submits the color picked from the palette", async () => {
    const user = userEvent.setup();
    let body: { color?: string } | undefined;
    server.use(
      http.post(`${BASE}/api/v1/tags`, async ({ request }) => {
        body = (await request.json()) as { color?: string };
        return envelope({ id: "new-tag-id" }, 201);
      })
    );

    render(<NewTagPage />, { preloadedState: DEVELOPER });
    await user.type(screen.getByLabelText(/Name/), "production");
    await user.click(screen.getByRole("combobox", { name: "Color" }));
    await user.click(await screen.findByRole("option", { name: "Violet" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(body?.color).toBe("violet"));
  });

  it("previews the tag as it is typed", async () => {
    const user = userEvent.setup();
    render(<NewTagPage />, { preloadedState: DEVELOPER });
    // Before a name is typed the chip stands in with a placeholder.
    expect(screen.getByText("tag")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/Name/), "prod");
    expect(await screen.findByText("prod")).toBeInTheDocument();
  });

  it("returns to the list after a successful save", async () => {
    const user = userEvent.setup();
    render(<NewTagPage />, { preloadedState: DEVELOPER });
    await user.type(screen.getByLabelText(/Name/), "production");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/tags"));
  });

  it("refuses the form for a viewer who cannot write tags", () => {
    render(<NewTagPage />, { preloadedState: REQUESTER });
    expect(screen.queryByLabelText(/Name/)).not.toBeInTheDocument();
  });
});
