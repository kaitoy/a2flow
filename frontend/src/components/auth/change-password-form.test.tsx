import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { store as appStore } from "@/store";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { ChangePasswordForm } from "./change-password-form";

const URL = "http://localhost:8000/api/v1/auth/password";

const USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: true,
  hasPassword: true,
  mustChangePassword: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user-1",
  updatedBy: "user-1",
} as User;

const authState = {
  auth: {
    user: USER,
    status: "authenticated" as const,
    selectedTenantId: null,
    impersonatedUserId: null,
    impersonatedBy: null,
  },
};

async function fill(current: string, next: string, confirm: string) {
  await userEvent.type(screen.getByLabelText(/^current password/i), current);
  await userEvent.type(screen.getByLabelText(/^new password/i), next);
  await userEvent.type(screen.getByLabelText(/^confirm new password/i), confirm);
  await userEvent.click(screen.getByRole("button", { name: "Change password" }));
}

describe("ChangePasswordForm", () => {
  it("changes the password and stores the updated user", async () => {
    let sent: unknown;
    server.use(
      http.post(URL, async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({
          meta: { requestId: "r", receivedAt: "", respondedAt: "" },
          data: { ...USER, mustChangePassword: false },
          error: null,
        });
      })
    );
    const onDone = vi.fn();
    const { store } = render(<ChangePasswordForm onDone={onDone} />, {
      preloadedState: authState,
    });

    await fill("old-password-123", "new-password-456", "new-password-456");

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(sent).toEqual({ currentPassword: "old-password-123", newPassword: "new-password-456" });
    expect(store.getState().auth.user?.mustChangePassword).toBe(false);
  });

  it("refuses a confirmation that does not match, without calling the API", async () => {
    const spy = vi.fn();
    server.use(http.post(URL, spy));
    render(<ChangePasswordForm />, { preloadedState: authState });

    await fill("old-password-123", "new-password-456", "new-password-789");

    expect(screen.getByText("The passwords do not match.")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("keeps the fields when the backend refuses the change", async () => {
    server.use(
      http.post(URL, () =>
        HttpResponse.json(
          {
            meta: { requestId: "r", receivedAt: "", respondedAt: "" },
            data: null,
            error: {
              code: "INVALID_CURRENT_PASSWORD",
              message: "The current password is incorrect.",
            },
          },
          { status: 422 }
        )
      )
    );
    const onDone = vi.fn();
    render(<ChangePasswordForm onDone={onDone} />, { preloadedState: authState });

    await fill("wrong-password-1", "new-password-456", "new-password-456");

    // api.ts toasts through the app-wide store, not the test's.
    await waitFor(() =>
      expect(appStore.getState().toast.items.at(-1)?.message).toBe(
        "The current password is incorrect."
      )
    );
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/^current password/i)).toHaveValue("wrong-password-1");
  });

  it("disables everything when told to", () => {
    render(<ChangePasswordForm disabled />, { preloadedState: authState });
    expect(screen.getByLabelText(/^current password/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Change password" })).toBeDisabled();
  });
});
