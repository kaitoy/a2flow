import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AdminPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

describe("AdminPage (welcome)", () => {
  it("renders the greeting heading", () => {
    render(<AdminPage />);
    expect(screen.getByRole("heading", { name: "Welcome to A2Flow" })).toBeInTheDocument();
  });

  it("renders a chat card linking to /new-session", () => {
    render(<AdminPage />);
    expect(screen.getByRole("link", { name: /Start chat/ })).toHaveAttribute(
      "href",
      "/new-session"
    );
  });

  it("renders cards linking to admin sections", () => {
    render(<AdminPage />);
    expect(screen.getByRole("link", { name: /Agent Skills/ })).toHaveAttribute(
      "href",
      "/admin/agent-skills"
    );
    expect(screen.getByRole("link", { name: /Users/ })).toHaveAttribute("href", "/admin/users");
  });
});
