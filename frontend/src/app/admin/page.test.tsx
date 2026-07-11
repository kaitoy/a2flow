import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { render, screen } from "@/test/test-utils";
import AdminPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
function authState(roles: Role[]): Partial<RootState> {
  return { auth: { user: { id: "u1", roles } as User, status: "authenticated" } };
}

describe("AdminPage (welcome)", () => {
  it("renders the greeting heading", () => {
    render(<AdminPage />, { preloadedState: authState(["super_admin"]) });
    expect(screen.getByRole("heading", { name: "Welcome to A2Flow" })).toBeInTheDocument();
  });

  it("renders a chat card linking to /sessions/new", () => {
    render(<AdminPage />, { preloadedState: authState([]) });
    expect(screen.getByRole("link", { name: /Start chat/ })).toHaveAttribute(
      "href",
      "/sessions/new"
    );
  });

  it("renders cards linking to admin sections for a super admin", () => {
    render(<AdminPage />, { preloadedState: authState(["super_admin"]) });
    expect(screen.getByRole("link", { name: /Agent Skills/ })).toHaveAttribute(
      "href",
      "/admin/agent-skills"
    );
    expect(screen.getByRole("link", { name: /Users/ })).toHaveAttribute("href", "/admin/users");
  });

  it("hides role-gated cards from a user without those roles", () => {
    render(<AdminPage />, { preloadedState: authState([]) });
    expect(screen.queryByRole("link", { name: /Users/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Secrets/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Agent Skills/ })).not.toBeInTheDocument();
    // Ungated sections stay visible to everyone.
    expect(screen.getByRole("link", { name: /Approvals/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Workflow Sessions/ })).toBeInTheDocument();
  });

  it("shows only the sections a developer may act on", () => {
    render(<AdminPage />, { preloadedState: authState(["developer"]) });
    expect(screen.getByRole("link", { name: /Agent Skills/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /MCP Servers/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Workflows/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Users/ })).not.toBeInTheDocument();
  });
});
