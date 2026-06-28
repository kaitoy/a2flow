import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Notification } from "@/lib/api";
import { render, screen, waitFor } from "@/test/test-utils";
import { NotificationPanel } from "./NotificationPanel";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

/** Build a Notification fixture with overridable fields. */
function makeNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "n1",
    userId: "user-1",
    type: "approval_request",
    title: "Plan ready for approval",
    body: "Waiting for your approval.",
    workflowSessionId: "ws-1",
    read: false,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
    ...overrides,
  };
}

/** Render harness wiring a real anchor button to the panel under test. */
function Harness({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLButtonElement | null>(null);
  return (
    <>
      <button type="button" ref={ref}>
        anchor
      </button>
      <NotificationPanel anchorRef={ref} open onClose={onClose} />
    </>
  );
}

describe("NotificationPanel", () => {
  it("renders the notifications from the store", async () => {
    render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: {
          items: [makeNotification()],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    await waitFor(() => expect(screen.getByText("Plan ready for approval")).toBeInTheDocument());
    expect(screen.getByText("Waiting for your approval.")).toBeInTheDocument();
  });

  it("shows an empty state when there are no notifications", async () => {
    render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: { items: [], unreadCount: 0, status: "idle" },
      },
    });
    await waitFor(() => expect(screen.getByText("No notifications")).toBeInTheDocument());
  });

  it("marks the item read, closes, and navigates to its workflow session", async () => {
    const onClose = vi.fn();
    pushMock.mockClear();
    const { store } = render(<Harness onClose={onClose} />, {
      preloadedState: {
        notifications: {
          items: [makeNotification()],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    await waitFor(() => screen.getByText("Plan ready for approval"));
    await screen.getByText("Plan ready for approval").click();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/workflow-sessions/ws-1"));
    expect(onClose).toHaveBeenCalled();
    expect(store.getState().notifications.unreadCount).toBe(0);
  });

  it("dismisses a single notification, removing it from the store", async () => {
    const { store } = render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: {
          items: [makeNotification()],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    await waitFor(() => screen.getByText("Plan ready for approval"));
    screen.getByRole("button", { name: "Dismiss" }).click();

    await waitFor(() => expect(store.getState().notifications.items).toHaveLength(0));
    expect(store.getState().notifications.unreadCount).toBe(0);
  });

  it("marks all notifications read, clearing the unread count and hiding its button", async () => {
    const { store } = render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: {
          items: [
            makeNotification({ id: "a", read: false }),
            makeNotification({ id: "b", read: false }),
          ],
          unreadCount: 2,
          status: "idle",
        },
      },
    });
    const button = await screen.findByRole("button", { name: "Mark all read" });
    button.click();

    await waitFor(() => expect(store.getState().notifications.unreadCount).toBe(0));
    expect(screen.queryByRole("button", { name: "Mark all read" })).not.toBeInTheDocument();
  });

  it("hides the mark-all-read button when nothing is unread", async () => {
    render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: {
          items: [makeNotification({ read: true })],
          unreadCount: 0,
          status: "idle",
        },
      },
    });
    await waitFor(() => screen.getByText("Plan ready for approval"));
    expect(screen.queryByRole("button", { name: "Mark all read" })).not.toBeInTheDocument();
  });
});
