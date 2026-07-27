import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import NotificationsPage from "./page";

describe("NotificationsPage", () => {
  it("renders the page heading and the full notification history", async () => {
    render(<NotificationsPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Notifications" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("No notifications yet.")).toBeInTheDocument());
  });
});
