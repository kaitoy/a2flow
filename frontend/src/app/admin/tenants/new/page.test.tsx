import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewTenantPage from "./page";

const CREATED_TENANT = {
  id: "new-tenant-id",
  name: "Acme Corp",
  slug: "acme-corp",
  enabled: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

/** Fill every required field of the create form with valid values. */
async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("textbox", { name: /name/i }), "Acme Corp");
  await user.type(screen.getByRole("textbox", { name: /slug/i }), "acme-corp");
}

describe("NewTenantPage", () => {
  it("renders name input", () => {
    render(<NewTenantPage />);
    expect(screen.getByRole("textbox", { name: /name/i })).toBeInTheDocument();
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

  it("shows validation error on blur when name is empty", async () => {
    const user = userEvent.setup();
    render(<NewTenantPage />);
    await user.click(screen.getByRole("textbox", { name: /name/i }));
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when slug has uppercase characters", async () => {
    const user = userEvent.setup();
    render(<NewTenantPage />);
    await user.type(screen.getByRole("textbox", { name: /slug/i }), "Acme-Corp");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(
        "http://localhost:8000/api/v1/tenants",
        () => new HttpResponse(null, { status: 409 })
      )
    );

    render(<NewTenantPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/409/)).toBeInTheDocument());
  });
});
