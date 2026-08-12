import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { UserPicker } from "./user-picker";

const BASE = "http://localhost:8000";

// `ADMIN` from `@/test/auth-state` carries no `tenantId` on its user, and the
// tenant filter this suite asserts on is derived from
// `auth.user.tenantId ?? auth.selectedTenantId` — so it needs a locally built
// preloaded state rather than the shared fixture (which other suites rely on
// staying tenant-less).
const ADMIN_IN_TENANT = {
  auth: {
    user: { id: "u1", roles: ["admin"], tenantId: "tenant-1" } as User,
    status: "authenticated" as const,
    selectedTenantId: null,
    impersonatedUserId: null,
    impersonatedBy: null,
  },
};

describe("UserPicker", () => {
  it("labels each user by name and username in the dialog", async () => {
    const user = userEvent.setup();
    render(<UserPicker value={[]} onChange={vi.fn()} />, { preloadedState: ADMIN_IN_TENANT });

    await user.click(screen.getByRole("button", { name: "Select members…" }));

    expect(
      await screen.findByRole("checkbox", { name: "Alice Smith (alice)" })
    ).toBeInTheDocument();
  });

  it("asks the server for the acting tenant's users only", async () => {
    const user = userEvent.setup();
    let query = "";
    server.use(
      http.get(`${BASE}/api/v1/users`, ({ request }) => {
        query = new URL(request.url).search;
        return envelope([]);
      })
    );
    render(<UserPicker value={[]} onChange={vi.fn()} />, { preloadedState: ADMIN_IN_TENANT });

    await user.click(screen.getByRole("button", { name: "Select members…" }));

    // Axios's default paramsSerializer (the `listConfig` helper every list page
    // relies on) deliberately un-escapes `%3A` back to `:` for readability, so
    // the wire format is `q=tenantId:eq:<id>`, not percent-encoded.
    await waitFor(() => expect(query).toContain("tenantId:eq:"));
  });

  it("shows an empty message when the tenant has no users", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/api/v1/users`, () => envelope([])));
    render(<UserPicker value={[]} onChange={vi.fn()} />, { preloadedState: ADMIN_IN_TENANT });

    await user.click(screen.getByRole("button", { name: "Select members…" }));

    expect(await screen.findByText("This tenant has no users to add.")).toBeInTheDocument();
  });
});
