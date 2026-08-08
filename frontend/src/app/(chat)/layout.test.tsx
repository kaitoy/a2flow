import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { render } from "@/test/test-utils";
import ChatLayout from "./layout";

vi.mock("@/components/auth/auth-provider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("@/components/ChatShell", () => ({
  ChatShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="chat-shell-mock">{children}</div>
  ),
}));

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
function authState(roles: Role[]): Partial<RootState> {
  return {
    auth: {
      user: { id: "u1", roles } as User,
      status: "authenticated",
      selectedTenantId: null,
      impersonatedUserId: null,
      impersonatedBy: null,
    },
  };
}

describe("ChatLayout", () => {
  it("renders the chat shell and children for a super_admin", () => {
    render(
      <ChatLayout>
        <div data-testid="panel">panel</div>
      </ChatLayout>,
      { preloadedState: authState(["super_admin"]) }
    );
    expect(screen.getByTestId("chat-shell-mock")).toBeInTheDocument();
    expect(screen.getByTestId("panel")).toBeInTheDocument();
  });

  it("shows an access-denied screen instead of the chat shell for a non-super_admin", () => {
    render(
      <ChatLayout>
        <div data-testid="panel">panel</div>
      </ChatLayout>,
      { preloadedState: authState(["developer"]) }
    );
    expect(screen.queryByTestId("chat-shell-mock")).not.toBeInTheDocument();
    expect(screen.queryByTestId("panel")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });
});
