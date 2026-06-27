import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import { Toaster } from "./toast";

describe("Toaster", () => {
  it("renders nothing when the queue is empty", () => {
    render(<Toaster />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders a queued toast message", () => {
    render(<Toaster />, {
      preloadedState: {
        toast: { items: [{ id: "t1", message: "Agent skill created", variant: "success" }] },
      },
    });
    expect(screen.getByText("Agent skill created")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
