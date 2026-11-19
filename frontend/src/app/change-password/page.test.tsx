import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import ChangePasswordPage from "./page";

function mockRouter() {
  const replace = vi.fn();
  vi.mocked(useRouter).mockReturnValue({
    push: vi.fn(),
    replace,
    back: vi.fn(),
    forward: vi.fn(),
    bfcacheId: "",
    prefetch: vi.fn(),
    refresh: vi.fn(),
  });
  return replace;
}

describe("ChangePasswordPage", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("goes on to the ?next page once the password is changed", async () => {
    const replace = mockRouter();
    window.history.replaceState(null, "", "/change-password?next=%2Fworkflows");
    render(<ChangePasswordPage />);

    await userEvent.type(screen.getByLabelText(/^current password/i), "old-password-123");
    await userEvent.type(screen.getByLabelText(/^new password/i), "new-password-456");
    await userEvent.type(screen.getByLabelText(/^confirm new password/i), "new-password-456");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/workflows"));
  });

  it("can sign out instead", async () => {
    const replace = mockRouter();
    render(<ChangePasswordPage />);

    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/signed-out"));
  });
});
