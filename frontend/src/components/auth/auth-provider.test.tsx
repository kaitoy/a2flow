import { http } from "msw";
import { usePathname, useRouter } from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { AuthProvider } from "./auth-provider";

const ME_URL = "http://localhost:8000/api/v1/auth/me";

const USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

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

describe("AuthProvider", () => {
  afterEach(() => {
    vi.mocked(usePathname).mockReturnValue("/");
    window.history.replaceState(null, "", "/");
  });

  it("renders the protected content for a signed-in user", async () => {
    render(
      <AuthProvider>
        <p>content</p>
      </AuthProvider>
    );
    expect(await screen.findByText("content")).toBeInTheDocument();
  });

  it("holds a user who must change their password at the change-password page", async () => {
    const replace = mockRouter();
    window.history.replaceState(null, "", "/workflows");
    server.use(
      http.get(ME_URL, () =>
        envelope({ user: { ...USER, mustChangePassword: true }, impersonatedBy: null })
      )
    );
    render(
      <AuthProvider>
        <p>content</p>
      </AuthProvider>
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/change-password?next=%2Fworkflows"));
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("lets that user see the change-password page itself", async () => {
    vi.mocked(usePathname).mockReturnValue("/change-password");
    server.use(
      http.get(ME_URL, () =>
        envelope({ user: { ...USER, mustChangePassword: true }, impersonatedBy: null })
      )
    );
    render(
      <AuthProvider>
        <p>form</p>
      </AuthProvider>
    );
    expect(await screen.findByText("form")).toBeInTheDocument();
  });

  it("does not hold an admin impersonating such a user", async () => {
    server.use(
      http.get(ME_URL, () =>
        envelope({
          user: { ...USER, mustChangePassword: true },
          impersonatedBy: { ...USER, id: "admin-1", mustChangePassword: false },
        })
      )
    );
    render(
      <AuthProvider>
        <p>content</p>
      </AuthProvider>
    );
    expect(await screen.findByText("content")).toBeInTheDocument();
  });
});
