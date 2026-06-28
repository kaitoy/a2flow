import { describe, expect, it } from "vitest";
import type { Notification } from "@/lib/api";
import reducer, {
  markAllReadLocal,
  markReadLocal,
  notificationsError,
  notificationsLoading,
  removeLocal,
  setNotifications,
} from "./notificationsSlice";

/** Build a Notification fixture with overridable fields. */
function makeNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "n1",
    userId: "user-1",
    type: "approval_request",
    title: "Plan ready for approval",
    body: null,
    workflowSessionId: "ws-1",
    read: false,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
    ...overrides,
  };
}

describe("notificationsSlice", () => {
  it("derives the unread count when notifications are set", () => {
    const state = reducer(
      undefined,
      setNotifications([
        makeNotification({ id: "a", read: false }),
        makeNotification({ id: "b", read: true }),
        makeNotification({ id: "c", read: false }),
      ])
    );
    expect(state.items).toHaveLength(3);
    expect(state.unreadCount).toBe(2);
    expect(state.status).toBe("idle");
  });

  it("marks a single notification read and decrements the unread count", () => {
    const initial = reducer(
      undefined,
      setNotifications([
        makeNotification({ id: "a", read: false }),
        makeNotification({ id: "b", read: false }),
      ])
    );
    const next = reducer(initial, markReadLocal("a"));
    expect(next.items.find((n) => n.id === "a")?.read).toBe(true);
    expect(next.unreadCount).toBe(1);
  });

  it("is a no-op when marking an already-read notification", () => {
    const initial = reducer(
      undefined,
      setNotifications([makeNotification({ id: "a", read: true })])
    );
    const next = reducer(initial, markReadLocal("a"));
    expect(next.unreadCount).toBe(0);
  });

  it("removes a single notification and recomputes the unread count", () => {
    const initial = reducer(
      undefined,
      setNotifications([
        makeNotification({ id: "a", read: false }),
        makeNotification({ id: "b", read: false }),
      ])
    );
    const next = reducer(initial, removeLocal("a"));
    expect(next.items.map((n) => n.id)).toEqual(["b"]);
    expect(next.unreadCount).toBe(1);
  });

  it("marks every notification read and zeroes the unread count", () => {
    const initial = reducer(
      undefined,
      setNotifications([
        makeNotification({ id: "a", read: false }),
        makeNotification({ id: "b", read: false }),
        makeNotification({ id: "c", read: true }),
      ])
    );
    const next = reducer(initial, markAllReadLocal());
    expect(next.items.every((n) => n.read)).toBe(true);
    expect(next.unreadCount).toBe(0);
  });

  it("tracks loading and error status without dropping items", () => {
    const withItems = reducer(undefined, setNotifications([makeNotification({ id: "a" })]));
    expect(reducer(withItems, notificationsLoading()).status).toBe("loading");
    const errored = reducer(withItems, notificationsError());
    expect(errored.status).toBe("error");
    expect(errored.items).toHaveLength(1);
  });
});
