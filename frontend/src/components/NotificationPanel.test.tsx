import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Notification } from "@/lib/api";
import { fireEvent, render, screen, waitFor } from "@/test/test-utils";
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
  const [open, setOpen] = useState(true);
  const ref = useRef<HTMLButtonElement | null>(null);
  return (
    <>
      {/* autoFocus simulates the anchor already holding focus from the click
          that opens the panel in real usage, which the a11y hook needs in
          order to capture it as the element to restore focus to on close. */}
      {/* biome-ignore lint/a11y/noAutofocus: test-only, simulates a pre-focused trigger */}
      <button type="button" ref={ref} autoFocus>
        anchor
      </button>
      <button type="button">outside</button>
      <NotificationPanel
        anchorRef={ref}
        open={open}
        onClose={() => {
          setOpen(false);
          onClose();
        }}
      />
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

  it("navigates to the workflow for a workflow-scoped notification", async () => {
    const onClose = vi.fn();
    pushMock.mockClear();
    render(<Harness onClose={onClose} />, {
      preloadedState: {
        notifications: {
          items: [
            makeNotification({
              type: "workflow_draft_ready",
              title: "Workflow draft ready",
              workflowSessionId: null,
              workflowId: "wf-1",
            }),
          ],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    await waitFor(() => screen.getByText("Workflow draft ready"));
    await screen.getByText("Workflow draft ready").click();

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/workflows/wf-1"));
    expect(onClose).toHaveBeenCalled();
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

  it("moves focus into the panel when it opens", async () => {
    render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: { items: [makeNotification()], unreadCount: 1, status: "idle" },
      },
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Mark all read" })).toHaveFocus()
    );
  });

  it("focuses the panel itself when there is nothing focusable inside it", async () => {
    render(<Harness onClose={vi.fn()} />, {
      preloadedState: { notifications: { items: [], unreadCount: 0, status: "idle" } },
    });
    await waitFor(() => expect(screen.getByRole("dialog")).toHaveFocus());
  });

  it("closes and returns focus to the anchor on Escape", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness onClose={onClose} />, {
      preloadedState: {
        notifications: {
          items: [makeNotification({ read: true })],
          unreadCount: 0,
          status: "idle",
        },
      },
    });
    await waitFor(() => screen.getByText("Plan ready for approval"));

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("anchor")).toHaveFocus());
  });

  it("closes on an outside pointerdown and returns focus to the anchor", async () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />, {
      preloadedState: {
        notifications: {
          items: [makeNotification({ read: true })],
          unreadCount: 0,
          status: "idle",
        },
      },
    });
    await waitFor(() => screen.getByText("Plan ready for approval"));

    fireEvent.pointerDown(document.body);

    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("anchor")).toHaveFocus());
  });

  it("wraps Shift+Tab from the first focusable element back to the last", async () => {
    const user = userEvent.setup();
    render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: {
          items: [makeNotification({ read: true })],
          unreadCount: 0,
          status: "idle",
        },
      },
    });
    // With no unread items, "Mark all read" is hidden: the only two focusable
    // elements are the notification's select button (first) and its Dismiss
    // button (last).
    await waitFor(() => screen.getByText("Plan ready for approval"));

    await user.tab({ shift: true });

    expect(screen.getByRole("button", { name: "Dismiss" })).toHaveFocus();
  });
});
