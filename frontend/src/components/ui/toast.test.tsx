import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
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

  it("does not auto-dismiss an error toast", async () => {
    vi.useFakeTimers();
    render(<Toaster />, {
      preloadedState: {
        toast: { items: [{ id: "t1", message: "Something broke", variant: "error" }] },
      },
    });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(screen.getByText("Something broke")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("dismisses an error toast when its close button is clicked", async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const { store } = render(<Toaster />, {
      preloadedState: {
        toast: { items: [{ id: "t1", message: "Something broke", variant: "error" }] },
      },
    });
    await user.click(screen.getByRole("button", { name: /dismiss/i }));
    await waitFor(() => expect(store.getState().toast.items).toHaveLength(0));
  });

  it("shows a count badge on a merged error toast", () => {
    render(<Toaster />, {
      preloadedState: {
        toast: { items: [{ id: "t1", message: "Something broke", variant: "error", count: 3 }] },
      },
    });
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("does not show a count badge for a single occurrence", () => {
    render(<Toaster />, {
      preloadedState: {
        toast: { items: [{ id: "t1", message: "Something broke", variant: "error" }] },
      },
    });
    expect(screen.queryByText("1")).not.toBeInTheDocument();
  });
});
