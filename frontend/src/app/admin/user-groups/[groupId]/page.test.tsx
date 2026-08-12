import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ADMIN, DEVELOPER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import UserGroupDetailPage from "./page";

const BASE = "http://localhost:8000";

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ groupId: "group-1" });
});

describe("UserGroupDetailPage", () => {
  it("prefills the form from the loaded group", async () => {
    render(<UserGroupDetailPage />, { preloadedState: ADMIN });
    await waitFor(() => expect(screen.getByLabelText(/^Name/)).toHaveValue("Developers"));
    expect(screen.getByLabelText("Description")).toHaveValue("People who build workflows");
    expect(screen.getByRole("checkbox", { name: "Developer" })).toBeChecked();
  });

  it("shows a chip for each current member", async () => {
    render(<UserGroupDetailPage />, { preloadedState: ADMIN });
    expect(await screen.findByText("Alice Smith (alice)")).toBeInTheDocument();
  });

  it("never offers super_admin among the roles a group can grant", async () => {
    render(<UserGroupDetailPage />, { preloadedState: ADMIN });
    await waitFor(() => screen.getByLabelText(/^Name/));
    expect(screen.queryByRole("checkbox", { name: "Super Admin" })).not.toBeInTheDocument();
  });

  it("submits the edited roles and members", async () => {
    let body: unknown;
    server.use(
      http.patch(`${BASE}/api/v1/user-groups/:groupId`, async ({ request }) => {
        body = await request.json();
        return envelope({ id: "group-1" });
      })
    );
    render(<UserGroupDetailPage />, { preloadedState: ADMIN });
    await waitFor(() => screen.getByRole("checkbox", { name: "Approver" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Approver" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(body).toMatchObject({
        name: "Developers",
        roles: ["developer", "approver"],
        memberIds: ["user-1"],
      })
    );
  });

  it("navigates back to the list on success", async () => {
    const push = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push } as unknown as ReturnType<typeof useRouter>);
    render(<UserGroupDetailPage />, { preloadedState: ADMIN });
    await waitFor(() => screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/user-groups"));
  });

  it("deletes the group after confirmation", async () => {
    let deleted = false;
    server.use(
      http.delete(`${BASE}/api/v1/user-groups/:groupId`, () => {
        deleted = true;
        return envelope(null);
      })
    );
    render(<UserGroupDetailPage />, { preloadedState: ADMIN });
    await waitFor(() => screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("renders read-only for a viewer who cannot write groups", async () => {
    render(<UserGroupDetailPage />, { preloadedState: DEVELOPER });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Developers" })).toBeInTheDocument()
    );
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("shows access denied when the group is forbidden", async () => {
    server.use(
      http.get(`${BASE}/api/v1/user-groups/:groupId`, () => envelopeErr("FORBIDDEN", "Nope", 403))
    );
    render(<UserGroupDetailPage />, { preloadedState: ADMIN });
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument()
    );
  });
});
