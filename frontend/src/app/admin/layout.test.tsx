import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { render, screen } from "@/test/test-utils";
import AdminLayout from "./layout";

vi.mock("@/components/auth/auth-provider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("@/components/AppHeader", () => ({
  AppHeader: () => <div data-testid="app-header-mock" />,
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
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

describe("AdminLayout", () => {
  it("shows the API Docs link for an admin, opening /api-doc in a new tab", () => {
    render(
      <AdminLayout>
        <div />
      </AdminLayout>,
      { preloadedState: authState(["admin"]) }
    );
    const link = screen.getByRole("link", { name: /API Docs/ });
    expect(link).toHaveAttribute("href", "/api-doc");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("shows the API Docs link for a super_admin", () => {
    render(
      <AdminLayout>
        <div />
      </AdminLayout>,
      { preloadedState: authState(["super_admin"]) }
    );
    expect(screen.getByRole("link", { name: /API Docs/ })).toBeInTheDocument();
  });

  it.each([
    "developer",
    "requester",
    "approver",
  ] as const)("hides the API Docs link from a %s", (role) => {
    render(
      <AdminLayout>
        <div />
      </AdminLayout>,
      { preloadedState: authState([role]) }
    );
    expect(screen.queryByRole("link", { name: /API Docs/ })).not.toBeInTheDocument();
  });

  it("still renders regular nav items alongside the footer", () => {
    render(
      <AdminLayout>
        <div />
      </AdminLayout>,
      { preloadedState: authState(["admin"]) }
    );
    expect(screen.getByRole("link", { name: /Users/ })).toBeInTheDocument();
  });
});
