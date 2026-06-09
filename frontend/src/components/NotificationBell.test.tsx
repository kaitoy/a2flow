import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { NotificationBell } from "./NotificationBell";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const BASE = "http://localhost:8000";

/** Build a notification envelope row. */
function row(id: string, read: boolean) {
  return {
    id,
    userId: "user-1",
    type: "approval_request",
    title: `Notification ${id}`,
    body: null,
    workflowSessionId: "ws-1",
    read,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

describe("NotificationBell", () => {
  it("shows an unread badge reflecting the fetched notifications", async () => {
    server.use(
      http.get(`${BASE}/api/v1/notifications`, () =>
        envelope([row("a", false), row("b", true), row("c", false)])
      )
    );
    render(<NotificationBell />);
    await waitFor(() => expect(screen.getByText("2")).toBeInTheDocument());
  });

  it("opens the panel listing notifications when clicked", async () => {
    server.use(http.get(`${BASE}/api/v1/notifications`, () => envelope([row("a", false)])));
    const user = userEvent.setup();
    render(<NotificationBell />);
    await waitFor(() => screen.getByText("1"));

    await user.click(screen.getByRole("button", { name: /notifications/i }));
    await waitFor(() => expect(screen.getByText("Notification a")).toBeInTheDocument());
  });

  it("renders no badge when there are no notifications", async () => {
    server.use(http.get(`${BASE}/api/v1/notifications`, () => envelope([])));
    const user = userEvent.setup();
    render(<NotificationBell />);

    await user.click(screen.getByRole("button", { name: /notifications/i }));
    await waitFor(() => expect(screen.getByText("No notifications")).toBeInTheDocument());
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
