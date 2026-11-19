import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { User } from "@/lib/api";
import { render, screen, waitFor } from "@/test/test-utils";
import { PasswordCard } from "./PasswordCard";

const USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: true,
  hasPassword: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user-1",
  updatedBy: "user-1",
} as User;

function authState(impersonatedBy: User | null = null) {
  return {
    auth: {
      user: USER,
      status: "authenticated" as const,
      selectedTenantId: null,
      impersonatedUserId: impersonatedBy ? USER.id : null,
      impersonatedBy,
    },
  };
}

describe("PasswordCard", () => {
  it("confirms a changed password with a toast", async () => {
    const { store } = render(<PasswordCard user={USER} />, { preloadedState: authState() });

    await userEvent.type(screen.getByLabelText(/^current password/i), "old-password-123");
    await userEvent.type(screen.getByLabelText(/^new password/i), "new-password-456");
    await userEvent.type(screen.getByLabelText(/^confirm new password/i), "new-password-456");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)?.message).toMatch(/password was changed/)
    );
  });

  it("is not shown for an account without a password", () => {
    render(<PasswordCard user={{ ...USER, hasPassword: false }} />, {
      preloadedState: authState(),
    });
    expect(screen.queryByLabelText(/^current password/i)).not.toBeInTheDocument();
  });

  it("is disabled while impersonating", () => {
    render(<PasswordCard user={USER} />, {
      preloadedState: authState({ ...USER, id: "admin-1" }),
    });
    expect(screen.getByLabelText(/^current password/i)).toBeDisabled();
    expect(screen.getByText(/while acting as another user/)).toBeInTheDocument();
  });
});
