import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import EditTenantPage from "./page";

const FULL_TENANT = {
  id: "tenant-1",
  displayName: "Acme Corp",
  name: "acme-corp",
  enabled: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

function setup() {
  vi.mocked(useParams).mockReturnValue({ tenantId: "tenant-1" });
}

describe("EditTenantPage", () => {
  it("prefills form with tenant data", async () => {
    setup();
    render(<EditTenantPage />);
    await waitFor(() => expect(screen.getByDisplayValue("Acme Corp")).toBeInTheDocument());
    expect(screen.getByDisplayValue("acme-corp")).toBeInTheDocument();
  });

  it("submits update api on form submit", async () => {
    setup();
    const patchSpy = vi.fn(() => envelope(FULL_TENANT));
    server.use(http.patch("http://localhost:8000/api/v1/tenants/:tenantId", patchSpy));

    render(<EditTenantPage />);
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
  });

  it("navigates to list after save", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });

    render(<EditTenantPage />);
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/tenants"));
  });

  it("signals tenantsChanged on update so pickers elsewhere refetch", async () => {
    setup();
    server.use(
      http.patch("http://localhost:8000/api/v1/tenants/:tenantId", () => envelope(FULL_TENANT))
    );

    const { store } = render(<EditTenantPage />);
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(store.getState().tenants.version).toBe(1));
  });

  it("signals tenantsChanged on delete so pickers elsewhere refetch", async () => {
    setup();
    server.use(http.delete("http://localhost:8000/api/v1/tenants/:tenantId", () => envelope(null)));

    const { store } = render(<EditTenantPage />);
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(store.getState().tenants.version).toBe(1));
  });

  it("calls delete api and navigates after confirm", async () => {
    setup();
    const pushMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: pushMock,
      replace: vi.fn(),
      back: vi.fn(),
      prefetch: vi.fn(),
      refresh: vi.fn(),
      forward: vi.fn(),
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/tenants/:tenantId", deleteSpy));

    render(<EditTenantPage />);
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/tenants");
  });

  it("renders name as a read-only field", async () => {
    setup();
    render(<EditTenantPage />);
    await waitFor(() => screen.getByDisplayValue("acme-corp"));
    expect(screen.getByRole("textbox", { name: /^name/i })).toBeDisabled();
  });

  it("omits name from the request body", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/tenants/:tenantId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_TENANT);
      })
    );

    render(<EditTenantPage />);
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).not.toHaveProperty("name");
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get(
        "http://localhost:8000/api/v1/tenants/:tenantId",
        () => new HttpResponse(null, { status: 404 })
      )
    );

    render(<EditTenantPage />);
    await waitFor(() => expect(screen.getByText(/404/)).toBeInTheDocument());
  });
});
