import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { ADMIN, DEVELOPER, SUPER_ADMIN } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewUserGroupPage from "./page";

const BASE = "http://localhost:8000";

/** Fill the required Name field. */
async function fillName(name = "Approvers") {
  await userEvent.type(screen.getByLabelText(/^Name/), name);
}

describe("NewUserGroupPage", () => {
  it("refuses a deep link from a non-admin viewer", () => {
    render(<NewUserGroupPage />, { preloadedState: DEVELOPER });
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("renders the form for an admin", () => {
    render(<NewUserGroupPage />, { preloadedState: ADMIN });
    expect(screen.getByLabelText(/^Name/)).toBeInTheDocument();
    expect(screen.getByText("Roles granted")).toBeInTheDocument();
  });

  it("never offers super_admin, even to a super admin viewer", () => {
    // A user group can never grant it; the backend rejects the attempt with 422.
    render(<NewUserGroupPage />, { preloadedState: SUPER_ADMIN });
    expect(screen.queryByRole("checkbox", { name: "Super Admin" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Developer" })).toBeInTheDocument();
  });

  it("validates the required name on blur", async () => {
    render(<NewUserGroupPage />, { preloadedState: ADMIN });
    await userEvent.click(screen.getByLabelText(/^Name/));
    await userEvent.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("submits the selected roles and members", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE}/api/v1/user-groups`, async ({ request }) => {
        body = await request.json();
        return envelope({ id: "new-group-id" }, 201);
      })
    );
    render(<NewUserGroupPage />, { preloadedState: ADMIN });
    await fillName();
    await userEvent.click(screen.getByRole("checkbox", { name: "Approver" }));
    await waitFor(() => screen.getByRole("checkbox", { name: "Alice Smith (alice)" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Alice Smith (alice)" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(body).toMatchObject({
        name: "Approvers",
        roles: ["approver"],
        memberIds: ["user-1"],
      })
    );
  });

  it("navigates back to the list on success", async () => {
    const push = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push } as unknown as ReturnType<typeof useRouter>);
    render(<NewUserGroupPage />, { preloadedState: ADMIN });
    await fillName();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/user-groups"));
  });
});
