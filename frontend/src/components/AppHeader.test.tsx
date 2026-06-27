import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
});
