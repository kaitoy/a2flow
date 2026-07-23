import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewTenantPage from "./page";

const CREATED_TENANT = {
  id: "new-tenant-id",
  displayName: "Acme Corp",
  name: "acme-corp",
  enabled: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

/** Fill every required field of the create form with valid values. */
async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("textbox", { name: /^display name/i }), "Acme Corp");
  await user.type(screen.getByRole("textbox", { name: /^name/i }), "acme-corp");
}

describe("NewTenantPage", () => {
  it("renders display name input", () => {
    render(<NewTenantPage />);
    expect(screen.getByRole("textbox", { name: /^display name/i })).toBeInTheDocument();
  });

  it("renders enabled checkbox checked by default", () => {
    render(<NewTenantPage />);
    expect(screen.getByRole("checkbox", { name: "Enabled" })).toBeChecked();
  });

  it("submits create api on form submit", async () => {
    const user = userEvent.setup();
    const createSpy = vi.fn(() => envelope(CREATED_TENANT, 201));
    server.use(http.post("http://localhost:8000/api/v1/tenants", createSpy));

    render(<NewTenantPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalled());
  });

  it("navigates to list on success", async () => {
    const user = userEvent.setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });

    render(<NewTenantPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/tenants"));
  });

  it("signals tenantsChanged on success so pickers elsewhere refetch", async () => {
    const user = userEvent.setup();
    const { store } = render(<NewTenantPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(store.getState().tenants.version).toBe(1));
  });

  it("shows validation error on blur when display name is empty", async () => {
    const user = userEvent.setup();
    render(<NewTenantPage />);
    await user.click(screen.getByRole("textbox", { name: /^display name/i }));
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when name has uppercase characters", async () => {
    const user = userEvent.setup();
    render(<NewTenantPage />);
    await user.type(screen.getByRole("textbox", { name: /^name/i }), "Acme-Corp");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/tenants", () =>
        envelopeErr("CONFLICT_UNIQUE", "Tenant name already in use", 409)
      )
    );

    render(<NewTenantPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Tenant name already in use",
        variant: "error",
      })
    );
  });
});
