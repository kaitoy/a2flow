import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import type { Notification } from "@/lib/api";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import { NotificationList } from "./NotificationList";

const BASE = "http://localhost:8000";

/** Build a Notification fixture with overridable fields. */
function makeNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "n1",
    tenantId: "tenant-1",
    userId: "user-1",
    type: "approval_request",
    title: "Plan ready for approval",
    body: null,
    workflowSessionId: "ws-1",
    workflowId: null,
    read: false,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
    ...overrides,
  };
}

/**
 * Serve the given rows from `GET /notifications`, honouring the `q` filter the
 * component sends, and record every request URL so tests can assert on the
 * query the component built.
 */
function serveNotifications(rows: Notification[]): { urls: URL[] } {
  const urls: URL[] = [];
  server.use(
    http.get(`${BASE}/api/v1/notifications`, ({ request }) => {
      const url = new URL(request.url);
      urls.push(url);
      const unreadOnly = url.searchParams.getAll("q").includes("read:eq:false");
      return envelope(unreadOnly ? rows.filter((n) => !n.read) : rows);
    })
  );
  return { urls };
}

describe("NotificationList", () => {
  it("lists every notification, read ones included", async () => {
    serveNotifications([
      makeNotification({ id: "a", title: "Still waiting", read: false }),
      makeNotification({ id: "b", title: "Already handled", read: true }),
    ]);
    render(<NotificationList />);

    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());
    expect(screen.getByText("Already handled")).toBeInTheDocument();
  });

  it("shows an empty state when there is no history", async () => {
    serveNotifications([]);
    render(<NotificationList />);

    await waitFor(() => expect(screen.getByText("No notifications yet.")).toBeInTheDocument());
  });

  it("requests unread rows only once the Read column filter is set to No", async () => {
    const { urls } = serveNotifications([
      makeNotification({ id: "a", title: "Still waiting", read: false }),
      makeNotification({ id: "b", title: "Already handled", read: true }),
    ]);
    const user = userEvent.setup();
    render(<NotificationList />);
    await waitFor(() => expect(screen.getByText("Already handled")).toBeInTheDocument());
    expect(urls[0].searchParams.getAll("q")).toEqual([]);

    await user.click(screen.getByRole("button", { name: /Read/ }));
    await user.click(await screen.findByRole("combobox", { name: "Filter Read" }));
    await user.click(await screen.findByRole("option", { name: "No" }));

    await waitFor(() => expect(screen.queryByText("Already handled")).not.toBeInTheDocument());
    expect(screen.getByText("Still waiting")).toBeInTheDocument();
    expect(urls.at(-1)?.searchParams.getAll("q")).toEqual(["read:eq:false"]);
  });

  it("keeps the read filter when a column filter is applied on top", async () => {
    const { urls } = serveNotifications([makeNotification({ title: "Still waiting" })]);
    const user = userEvent.setup();
    render(<NotificationList />);
    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Read/ }));
    await user.click(await screen.findByRole("combobox", { name: "Filter Read" }));
    await user.click(await screen.findByRole("option", { name: "No" }));
    await waitFor(() => expect(urls.at(-1)?.searchParams.getAll("q")).toEqual(["read:eq:false"]));

    await user.click(screen.getByRole("button", { name: /Title/ }));
    await user.type(await screen.findByPlaceholderText(/filter/i), "plan");

    await waitFor(() => {
      const q = urls.at(-1)?.searchParams.getAll("q") ?? [];
      expect(q).toContain("read:eq:false");
      expect(q).toContain("title:like:plan");
    });
  });

  it("sorts by a column when its header sort action is used", async () => {
    const { urls } = serveNotifications([makeNotification({ title: "Still waiting" })]);
    const user = userEvent.setup();
    render(<NotificationList />);
    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Created/ }));
    await user.click(await screen.findByRole("button", { name: /Sort ascending/i }));

    await waitFor(() => expect(urls.at(-1)?.searchParams.get("s")).toBe("createdAt"));
  });

  it("marks a row read and keeps the toolbar bell's badge in step", async () => {
    let patched: { id: string; body: unknown } | null = null;
    serveNotifications([makeNotification({ id: "a", title: "Still waiting", read: false })]);
    server.use(
      http.patch(`${BASE}/api/v1/notifications/:id`, async ({ params, request }) => {
        patched = { id: params.id as string, body: await request.json() };
        return envelope(makeNotification({ id: "a", title: "Still waiting", read: true }));
      })
    );
    const user = userEvent.setup();
    const { store } = render(<NotificationList />, {
      preloadedState: {
        notifications: {
          items: [makeNotification({ id: "a", title: "Still waiting", read: false })],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Mark as read" }));

    await waitFor(() => expect(store.getState().notifications.unreadCount).toBe(0));
    expect(patched).toEqual({ id: "a", body: { read: true } });
  });

  it("deletes a row only after the confirm dialog is accepted", async () => {
    const deleted: string[] = [];
    serveNotifications([makeNotification({ id: "a", title: "Still waiting" })]);
    server.use(
      http.delete(`${BASE}/api/v1/notifications/:id`, ({ params }) => {
        deleted.push(params.id as string);
        return envelope(null);
      })
    );
    const user = userEvent.setup();
    const { store } = render(<NotificationList />, {
      preloadedState: {
        notifications: {
          items: [makeNotification({ id: "a", title: "Still waiting" })],
          unreadCount: 1,
          status: "idle",
        },
      },
    });
    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Still waiting/)).toBeInTheDocument();
    expect(deleted).toEqual([]);

    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(deleted).toEqual(["a"]));
    expect(store.getState().notifications.items).toHaveLength(0);
  });

  it("leaves the row alone when the confirm dialog is cancelled", async () => {
    const deleted: string[] = [];
    serveNotifications([makeNotification({ id: "a", title: "Still waiting" })]);
    server.use(
      http.delete(`${BASE}/api/v1/notifications/:id`, ({ params }) => {
        deleted.push(params.id as string);
        return envelope(null);
      })
    );
    const user = userEvent.setup();
    render(<NotificationList />);
    await waitFor(() => expect(screen.getByText("Still waiting")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(deleted).toEqual([]);
    expect(screen.getByText("Still waiting")).toBeInTheDocument();
  });

  it("pages through the history with the pagination controls", async () => {
    // A full page means there may be more behind it, which is what enables Next.
    const fullPage = Array.from({ length: 20 }, (_, i) =>
      makeNotification({ id: `n${i}`, title: `Notification ${i}` })
    );
    const { urls } = serveNotifications(fullPage);
    const user = userEvent.setup();
    render(<NotificationList />);
    await waitFor(() => expect(screen.getByText("Notification 0")).toBeInTheDocument());
    expect(urls[0].searchParams.get("offset")).toBe("0");
    expect(urls[0].searchParams.get("limit")).toBe("20");
    expect(screen.getByRole("button", { name: "← Previous" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next →" }));

    await waitFor(() => expect(urls.at(-1)?.searchParams.get("offset")).toBe("20"));
    expect(screen.getByRole("button", { name: "← Previous" })).toBeEnabled();
  });

  it("hides the mark-as-read action on rows that are already read", async () => {
    serveNotifications([makeNotification({ id: "b", title: "Already handled", read: true })]);
    render(<NotificationList />);
    await waitFor(() => expect(screen.getByText("Already handled")).toBeInTheDocument());

    expect(screen.queryByRole("button", { name: "Mark as read" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });
});
