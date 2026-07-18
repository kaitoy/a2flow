import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { render, screen, waitFor } from "@/test/test-utils";
import { TenantField } from "./tenant-field";

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
function authState(roles: Role[]): Partial<RootState> {
  return { auth: { user: { id: "u1", roles } as User, status: "authenticated" } };
}

describe("TenantField", () => {
  it("renders nothing for a non-super-admin viewer", () => {
    render(<TenantField value={null} onChange={vi.fn()} />, {
      preloadedState: authState(["admin"]),
    });
    expect(screen.queryByLabelText("Tenant")).not.toBeInTheDocument();
  });

  it("renders a tenant select populated with options for a super-admin viewer", async () => {
    render(<TenantField value={null} onChange={vi.fn()} />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Acme Corp" })).toBeInTheDocument();
    });
  });

  it("selects the currently assigned tenant", async () => {
    render(<TenantField value="tenant-1" onChange={vi.fn()} />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Tenant" })).toHaveValue("tenant-1");
    });
  });

  it("reports the next selection when the tenant changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TenantField value={null} onChange={onChange} />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Acme Corp" })).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "Tenant" }), "tenant-1");
    expect(onChange).toHaveBeenCalledWith("tenant-1");
  });
});
