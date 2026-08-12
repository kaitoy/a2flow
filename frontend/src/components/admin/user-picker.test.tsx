import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { UserPicker } from "./user-picker";

const BASE = "http://localhost:8000";

/** Build a user row for the list endpoint. */
function user(overrides: Record<string, unknown>) {
  return {
    id: "u1",
    username: "alice",
    firstName: "Alice",
    lastName: "Smith",
    email: "alice@example.com",
    enabled: true,
    emailVerified: false,
    tenantId: "tenant-1",
    roles: [],
    groupRoles: [],
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
    ...overrides,
  };
}

describe("UserPicker", () => {
  it("labels each user by name and username", async () => {
    render(<UserPicker value={[]} onChange={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "Alice Smith (alice)" })).toBeInTheDocument()
    );
  });

  it("omits platform-scoped users, which can never be members", async () => {
    // A super admin (and the seeded system user) carry no tenantId, and a group
    // belongs to exactly one tenant — the backend rejects them with 422.
    server.use(
      http.get(`${BASE}/api/v1/users`, () =>
        envelope([
          user({ id: "u1", username: "alice" }),
          user({ id: "root", username: "root", tenantId: null, roles: ["super_admin"] }),
        ])
      )
    );
    render(<UserPicker value={[]} onChange={vi.fn()} />);
    await waitFor(() => screen.getByRole("checkbox", { name: "Alice Smith (alice)" }));
    expect(screen.queryByRole("checkbox", { name: /root/ })).not.toBeInTheDocument();
  });

  it("shows an empty message when the tenant has no users", async () => {
    server.use(http.get(`${BASE}/api/v1/users`, () => envelope([])));
    render(<UserPicker value={[]} onChange={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText("This tenant has no users to add.")).toBeInTheDocument()
    );
  });
});
