import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RouteErrorFallback } from "./route-error-fallback";

describe("RouteErrorFallback", () => {
  it("renders the default title and description", () => {
    render(<RouteErrorFallback reset={vi.fn()} fill="screen" />);
    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByText("An unexpected error occurred.")).toBeInTheDocument();
  });

  it("renders a custom title and description", () => {
    render(
      <RouteErrorFallback
        reset={vi.fn()}
        fill="screen"
        title="Couldn't load this page"
        description="Try again in a moment."
      />
    );
    expect(screen.getByRole("heading", { name: "Couldn't load this page" })).toBeInTheDocument();
    expect(screen.getByText("Try again in a moment.")).toBeInTheDocument();
  });

  it("calls reset when 'Try again' is clicked", async () => {
    const reset = vi.fn();
    render(<RouteErrorFallback reset={reset} fill="screen" />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });

  it("does not render a home link when homeHref/homeLabel are omitted", () => {
    render(<RouteErrorFallback reset={vi.fn()} fill="screen" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders a home link when homeHref and homeLabel are both provided", () => {
    render(
      <RouteErrorFallback
        reset={vi.fn()}
        fill="screen"
        homeHref="/admin"
        homeLabel="Go to dashboard"
      />
    );
    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute("href", "/admin");
  });
});
