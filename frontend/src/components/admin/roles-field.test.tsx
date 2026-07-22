import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { render, screen } from "@/test/test-utils";
import { RolesField } from "./roles-field";

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
function authState(roles: Role[]): Partial<RootState> {
  return { auth: { user: { id: "u1", roles } as User, status: "authenticated" } };
}

describe("RolesField", () => {
  it("renders a checkbox per non-super-admin role", () => {
    render(<RolesField value={[]} onChange={vi.fn()} />, {
      preloadedState: authState(["admin"]),
    });
    for (const label of ["Admin", "Developer", "Requester", "Approver"]) {
      expect(screen.getByRole("checkbox", { name: label })).toBeInTheDocument();
    }
  });

  it("checks the roles currently held", () => {
    render(<RolesField value={["developer"]} onChange={vi.fn()} />, {
      preloadedState: authState(["admin"]),
    });
    expect(screen.getByRole("checkbox", { name: "Developer" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Approver" })).not.toBeChecked();
  });

  it("reports the next selection when a role is toggled", async () => {
    const onChange = vi.fn();
    render(<RolesField value={[]} onChange={onChange} />, {
      preloadedState: authState(["admin"]),
    });
    await userEvent.click(screen.getByRole("checkbox", { name: "Requester" }));
    expect(onChange).toHaveBeenCalledWith(["requester"]);
  });

  it("hides the super_admin option for a non-super-admin viewer", () => {
    render(<RolesField value={[]} onChange={vi.fn()} />, {
      preloadedState: authState(["admin"]),
    });
    expect(screen.queryByRole("checkbox", { name: "Super Admin" })).not.toBeInTheDocument();
  });

  it("shows the super_admin option for a super-admin viewer", () => {
    render(<RolesField value={[]} onChange={vi.fn()} />, {
      preloadedState: authState(["super_admin"]),
    });
    expect(screen.getByRole("checkbox", { name: "Super Admin" })).toBeInTheDocument();
  });

  it("preserves an existing super_admin grant when a non-super-admin toggles another role", async () => {
    const onChange = vi.fn();
    render(<RolesField value={["super_admin", "developer"]} onChange={onChange} />, {
      preloadedState: authState(["admin"]),
    });
    await userEvent.click(screen.getByRole("checkbox", { name: "Approver" }));
    const reported = onChange.mock.calls[0][0];
    expect(reported).toHaveLength(3);
    expect(reported).toEqual(expect.arrayContaining(["super_admin", "developer", "approver"]));
  });
});
