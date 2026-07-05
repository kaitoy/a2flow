import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GlobalErrorContent } from "./global-error";

describe("GlobalErrorContent", () => {
  it("renders the fallback and wires the reset action", async () => {
    const reset = vi.fn();
    render(<GlobalErrorContent reset={reset} />);
    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });
});
