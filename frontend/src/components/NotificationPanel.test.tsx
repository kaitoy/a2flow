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
    tenantId: "tenant-1",
    userId: "user-1",
    type: "approval_request",
    title: "Plan ready for approval",
    body: "Waiting for your approval.",
    workflowExecutionId: "execution-1",
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
    await waitFor(() => expect(screen.getByText("No unread notifications")).toBeInTheDocument());
  });

  it("hides notifications that are already read", async () => {
    render(<Harness onClose={vi.fn()} />, {
      preloadedState: {
        notifications: {
          items: [
            makeNotification({ id: "a", title: "Already handled", read: true }),
            makeNotification({ id: "b", title: "Still waiting", read: false }),
          ],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());
    expect(screen.queryByText("Already handled")).not.toBeInTheDocument();
  });

  it("marks the item read, closes, and navigates to its workflow execution", async () => {
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

    await waitFor(() =>
      expect(pushMock).toHaveBeenCalledWith("/workflow-executions/execution-1/session")
    );
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
              workflowExecutionId: null,
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

  it("marks a single notification read, dropping it from the list without deleting it", async () => {
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
    screen.getByRole("button", { name: "Mark as read" }).click();

    await waitFor(() => expect(store.getState().notifications.unreadCount).toBe(0));
    // The record survives -- only the popup stops showing it. Deleting is the
    // profile list's job.
    expect(store.getState().notifications.items).toHaveLength(1);
    expect(store.getState().notifications.items[0].read).toBe(true);
    expect(screen.queryByText("Plan ready for approval")).not.toBeInTheDocument();
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
    // An all-read store leaves the popup empty, since it only lists unread items.
    await waitFor(() => screen.getByText("No unread notifications"));
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
          items: [makeNotification()],
          unreadCount: 1,
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
          items: [makeNotification()],
          unreadCount: 1,
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
          items: [makeNotification()],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    // Focus order inside the panel: "Mark all read" (first), the notification's
    // select button, then its "Mark as read" button (last).
    await waitFor(() => screen.getByText("Plan ready for approval"));

    await user.tab({ shift: true });

    expect(screen.getByRole("button", { name: "Mark as read" })).toHaveFocus();
  });
});
