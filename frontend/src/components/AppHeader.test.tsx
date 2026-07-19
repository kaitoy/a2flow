import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { render } from "@/test/test-utils";
import { AppHeader } from "./AppHeader";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("./ThemeToggle", () => ({
  ThemeToggle: () => <div data-testid="theme-toggle-mock" />,
}));

describe("AppHeader", () => {
  it("renders the logo, notification bell, profile button, and theme toggle", () => {
    render(<AppHeader />);
    expect(screen.getByAltText("A2Flow logo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /account/i })).toBeInTheDocument();
    expect(screen.getByTestId("theme-toggle-mock")).toBeInTheDocument();
  });

  it("links the logo to the /admin welcome page", () => {
    render(<AppHeader />);
    expect(screen.getByRole("link", { name: "A2Flow home" })).toHaveAttribute("href", "/admin");
  });

  it("does not render the tenant switcher for a non-super-admin viewer", () => {
    const preloadedState: Partial<RootState> = {
      auth: {
        user: { id: "u1", roles: ["admin"] } as User,
        status: "authenticated",
        selectedTenantId: null,
      },
    };
    render(<AppHeader />, { preloadedState });
    expect(screen.queryByLabelText("Acting tenant")).not.toBeInTheDocument();
  });

  it("renders the tenant switcher for a super-admin viewer", async () => {
    const preloadedState: Partial<RootState> = {
      auth: {
        user: { id: "u1", roles: ["super_admin"] } as User,
        status: "authenticated",
        selectedTenantId: null,
      },
    };
    render(<AppHeader />, { preloadedState });
    await waitFor(() => {
      expect(screen.getByLabelText("Acting tenant")).toBeInTheDocument();
    });
  });
});
