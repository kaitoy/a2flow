import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Tenant, User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { SELECTED_TENANT_STORAGE_KEY } from "@/store/authSlice";
import { tenantsChanged } from "@/store/tenantsSlice";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { TenantSwitcher } from "./tenant-switcher";

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
function authState(roles: Role[], selectedTenantId: string | null = null): Partial<RootState> {
  return {
    auth: { user: { id: "u1", roles } as User, status: "authenticated", selectedTenantId },
  };
}

const reloadMock = vi.fn();

beforeEach(() => {
  reloadMock.mockClear();
  Object.defineProperty(window, "location", {
    value: { ...window.location, reload: reloadMock },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  window.localStorage.removeItem(SELECTED_TENANT_STORAGE_KEY);
});

describe("TenantSwitcher", () => {
  it("renders nothing for a non-super-admin viewer", () => {
    render(<TenantSwitcher />, { preloadedState: authState(["admin"]) });
    expect(screen.queryByLabelText("Acting tenant")).not.toBeInTheDocument();
  });

  it("renders a select populated with every tenant for a super-admin viewer", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1, TENANT_2])));
    render(<TenantSwitcher />, { preloadedState: authState(["super_admin"]) });
    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Acme Corp" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Globex" })).toBeInTheDocument();
    });
  });

  it("auto-selects the first tenant when nothing is selected yet", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1, TENANT_2])));
    render(<TenantSwitcher />, { preloadedState: authState(["super_admin"]) });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Acting tenant" })).toHaveValue("tenant-1");
    });
  });

  it("keeps an already-selected tenant instead of overriding it", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1, TENANT_2])));
    render(<TenantSwitcher />, { preloadedState: authState(["super_admin"], "tenant-2") });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Acting tenant" })).toHaveValue("tenant-2");
    });
  });

  it("falls back to auto-select when the persisted tenant no longer exists", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1])));
    render(<TenantSwitcher />, {
      preloadedState: authState(["super_admin"], "stale-tenant"),
    });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Acting tenant" })).toHaveValue("tenant-1");
    });
  });

  it("persists a new selection to localStorage and reloads the page", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1, TENANT_2])));
    render(<TenantSwitcher />, { preloadedState: authState(["super_admin"]) });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Acting tenant" })).toHaveValue("tenant-1");
    });

    await user.selectOptions(screen.getByRole("combobox", { name: "Acting tenant" }), "tenant-2");

    expect(window.localStorage.getItem(SELECTED_TENANT_STORAGE_KEY)).toBe("tenant-2");
    expect(reloadMock).toHaveBeenCalledOnce();
  });

  it("does not reload the page for the initial auto-select", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1, TENANT_2])));
    render(<TenantSwitcher />, { preloadedState: authState(["super_admin"]) });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Acting tenant" })).toHaveValue("tenant-1");
    });
    expect(reloadMock).not.toHaveBeenCalled();
  });

  it("refetches the tenant list when tenants.version changes, without remounting", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([TENANT_1])));
    const { store } = render(<TenantSwitcher />, { preloadedState: authState(["super_admin"]) });
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

  it("shows a disabled placeholder when there are no tenants", async () => {
    server.use(http.get(`${BASE}/api/v1/tenants`, () => envelope([])));
    render(<TenantSwitcher />, { preloadedState: authState(["super_admin"]) });
    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Acting tenant" })).toBeDisabled();
    });
  });
});
