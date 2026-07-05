import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import RouteError from "./error";

describe("Admin RouteError", () => {
  it("renders the fallback and wires the reset action", async () => {
    const reset = vi.fn();
    render(<RouteError error={new Error("boom")} reset={reset} />);
    expect(screen.getByRole("heading")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });

  it("links back to the admin dashboard", () => {
    render(<RouteError error={new Error("boom")} reset={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Back to dashboard" })).toHaveAttribute(
      "href",
      "/admin"
    );
  });
});
