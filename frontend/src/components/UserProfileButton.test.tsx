import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { render, screen, waitFor } from "@/test/test-utils";
import { UserProfileButton } from "./UserProfileButton";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

/** Build a User fixture for the auth slice. */
function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: "user-1",
    username: "alice",
    firstName: "Alice",
    lastName: "Smith",
    email: "alice@example.com",
    enabled: true,
    emailVerified: false,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
    ...overrides,
  };
}

describe("UserProfileButton", () => {
  it("opens the account menu when clicked", async () => {
    const user = userEvent.setup();
    render(<UserProfileButton />, {
      preloadedState: { auth: { user: makeUser(), status: "authenticated" } },
    });

    await user.click(screen.getByRole("button", { name: "Account" }));

    await waitFor(() => expect(screen.getByRole("menu")).toBeInTheDocument());
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
  });
});
