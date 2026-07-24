import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render } from "@/test/test-utils";
import { ImpersonationIndicator } from "./ImpersonationIndicator";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn() })),
}));

const TARGET = {
  id: "target-1",
  username: "target",
  firstName: "T",
  lastName: "User",
  email: "target@example.com",
  enabled: true,
  emailVerified: false,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
} as User;

const ACTOR = {
  id: "actor-1",
  username: "actor",
  firstName: "A",
  lastName: "Admin",
  email: "actor@example.com",
  enabled: true,
  emailVerified: false,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
} as User;

function impersonatingState(): Partial<RootState> {
  return {
    auth: {
      user: TARGET,
      status: "authenticated",
      selectedTenantId: null,
      impersonatedUserId: TARGET.id,
      impersonatedBy: ACTOR,
    },
  };
}

describe("ImpersonationIndicator", () => {
  it("renders nothing when not impersonating", () => {
    render(<ImpersonationIndicator />, {
      preloadedState: {
        auth: {
          user: ACTOR,
          status: "authenticated",
          selectedTenantId: null,
          impersonatedUserId: null,
          impersonatedBy: null,
        },
      },
    });
    expect(screen.queryByText(/Acting as/)).not.toBeInTheDocument();
  });

  it("shows the acting-as badge and stop control while impersonating", () => {
    render(<ImpersonationIndicator />, { preloadedState: impersonatingState() });
    expect(screen.getByText(`Acting as ${TARGET.username}`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop impersonating" })).toBeInTheDocument();
  });

  it("stops impersonating and navigates to /admin on click", async () => {
    const push = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push, replace: vi.fn() } as never);
    const stopSpy = vi.fn(() => envelope({ user: ACTOR, impersonatedBy: null }));
    server.use(http.delete("http://localhost:8000/api/v1/auth/impersonate", stopSpy));

    const user = userEvent.setup();
    const { store } = render(<ImpersonationIndicator />, {
      preloadedState: impersonatingState(),
    });

    await user.click(screen.getByRole("button", { name: "Stop impersonating" }));

    await waitFor(() => expect(stopSpy).toHaveBeenCalled());
    await waitFor(() => expect(store.getState().auth.impersonatedBy).toBeNull());
    expect(push).toHaveBeenCalledWith("/admin");
  });
});
