import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { Tenant, User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { tenantsChanged } from "@/store/tenantsSlice";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { TenantField } from "./tenant-field";

const BASE = "http://localhost:8000";

const TENANT_1: Tenant = {
  id: "tenant-1",
  displayName: "Acme Corp",
  name: "acme-corp",
  enabled: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const TENANT_2: Tenant = {
  ...TENANT_1,
  id: "tenant-2",
  displayName: "Globex",
  name: "globex",
};

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

  it("refetches the tenant list when tenants.version changes, without remounting", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1])));
    const { store } = render(<TenantField value={null} onChange={vi.fn()} />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Acme Corp" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("option", { name: "Globex" })).not.toBeInTheDocument();

    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1, TENANT_2])));
    store.dispatch(tenantsChanged());

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Globex" })).toBeInTheDocument();
    });
  });

  it("disables the select when disabled is true", () => {
    render(<TenantField value={null} onChange={vi.fn()} disabled />, {
      preloadedState: authState(["super_admin"]),
    });
    expect(screen.getByRole("combobox", { name: "Tenant" })).toBeDisabled();
  });

  it("does not call onChange when already unassigned and disabled", async () => {
    const onChange = vi.fn();
    render(<TenantField value={null} onChange={onChange} disabled />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Tenant" })).toBeDisabled();
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("clears a previously selected tenant when rendered already disabled", async () => {
    const onChange = vi.fn();
    render(<TenantField value="tenant-1" onChange={onChange} disabled />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(null);
    });
  });

  it("clears the tenant when transitioning to disabled", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<TenantField value="tenant-1" onChange={onChange} />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Tenant" })).toHaveValue("tenant-1");
    });
    expect(onChange).not.toHaveBeenCalled();
    rerender(<TenantField value="tenant-1" onChange={onChange} disabled />);
    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(null);
    });
  });

  it("disables the select when locked, without clearing the value", async () => {
    const onChange = vi.fn();
    render(<TenantField value="tenant-1" onChange={onChange} locked />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Tenant" })).toBeDisabled();
    });
    expect(screen.getByRole("combobox", { name: "Tenant" })).toHaveValue("tenant-1");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not clear the tenant when rendered already locked", async () => {
    const onChange = vi.fn();
    render(<TenantField value="tenant-1" onChange={onChange} locked />, {
      preloadedState: authState(["super_admin"]),
    });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Tenant" })).toBeDisabled();
    });
    expect(onChange).not.toHaveBeenCalled();
  });
});
