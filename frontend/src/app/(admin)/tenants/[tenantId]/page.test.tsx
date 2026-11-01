import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { SUPER_ADMIN } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import TenantDetailPage from "./page";

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

/** Serve `tenant` and capture the PATCH body the page sends. */
function capturePatch(tenant: object) {
  const captured: { body: Record<string, unknown> | null } = { body: null };
  server.use(
    http.get("http://localhost:8000/api/v1/tenants/:tenantId", () => envelope(tenant)),
    http.patch("http://localhost:8000/api/v1/tenants/:tenantId", async ({ request }) => {
      captured.body = (await request.json()) as Record<string, unknown>;
      return envelope(tenant);
    })
  );
  return captured;
}

/** Render the page as a super admin — the role every tenant write requires. */
function renderPage() {
  return render(<TenantDetailPage />, { preloadedState: SUPER_ADMIN });
}

describe("TenantDetailPage", () => {
  it("titles the page and ends the breadcrumb trail with the tenant's display name", async () => {
    setup();
    renderPage();
    expect(await screen.findByRole("heading", { name: "Acme Corp" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getByText("Acme Corp")).toHaveAttribute("aria-current", "page");
  });

  it("prefills form with tenant data", async () => {
    setup();
    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue("Acme Corp")).toBeInTheDocument());
    expect(screen.getByText("acme-corp")).toBeInTheDocument();
  });

  it("submits update api on form submit", async () => {
    setup();
    const patchSpy = vi.fn(() => envelope(FULL_TENANT));
    server.use(http.patch("http://localhost:8000/api/v1/tenants/:tenantId", patchSpy));

    renderPage();
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
      bfcacheId: "",
    });

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/tenants"));
  });

  it("signals tenantsChanged on update so pickers elsewhere refetch", async () => {
    setup();
    server.use(
      http.patch("http://localhost:8000/api/v1/tenants/:tenantId", () => envelope(FULL_TENANT))
    );

    const { store } = renderPage();
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(store.getState().tenants.version).toBe(1));
  });

  it("signals tenantsChanged on delete so pickers elsewhere refetch", async () => {
    setup();
    server.use(http.delete("http://localhost:8000/api/v1/tenants/:tenantId", () => envelope(null)));

    const { store } = renderPage();
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
      bfcacheId: "",
    });
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/tenants/:tenantId", deleteSpy));

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/tenants");
  });

  it("renders the immutable name as a value, not an input, even for a super admin", async () => {
    setup();
    renderPage();
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    expect(screen.queryByRole("textbox", { name: /^name/i })).not.toBeInTheDocument();
    expect(screen.getByText("acme-corp")).toHaveClass("bg-surface-dim/40");
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

    renderPage();
    await waitFor(() => screen.getByDisplayValue("Acme Corp"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).not.toHaveProperty("name");
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get("http://localhost:8000/api/v1/tenants/:tenantId", () =>
        envelopeErr("NOT_FOUND", "Tenant not found", 404)
      )
    );

    renderPage();
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Tenant not found",
        variant: "error",
      })
    );
  });

  describe("tenant settings", () => {
    it("prefills and sends the sign-in lockout", async () => {
      setup();
      const captured = capturePatch({
        ...FULL_TENANT,
        loginMaxFailures: 3,
        loginLockoutMinutes: 45,
      });
      renderPage();
      const maxFailures = await screen.findByLabelText(/Failed Sign-ins Before Lockout/);
      expect(maxFailures).toHaveValue("3");
      expect(screen.getByLabelText(/Lockout Minutes/)).toHaveValue("45");
      await userEvent.clear(maxFailures);
      await userEvent.type(maxFailures, "8");
      await userEvent.click(screen.getByRole("button", { name: /save/i }));

      await waitFor(() => expect(captured.body).not.toBeNull());
      expect(captured.body).toMatchObject({ loginMaxFailures: 8, loginLockoutMinutes: 45 });
    });

    it("leaves the Vault connection to the Tenant Settings page", async () => {
      setup();
      const captured = capturePatch(FULL_TENANT);
      renderPage();
      await screen.findByLabelText(/Failed Sign-ins Before Lockout/);
      expect(screen.queryByLabelText("Vault Address")).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /save/i }));

      await waitFor(() => expect(captured.body).not.toBeNull());
      expect(Object.keys(captured.body ?? {}).some((key) => key.startsWith("vault"))).toBe(false);
    });
  });

  describe("global Vault credential", () => {
    const GLOBAL_VAULT_TENANT = {
      ...FULL_TENANT,
      globalVaultAuthMethod: "token",
      globalVaultRoleId: null,
      globalVaultApproleMount: null,
      globalVaultCredentialSet: true,
    };

    it("keeps a saved token by leaving the field blank", async () => {
      setup();
      const captured = capturePatch(GLOBAL_VAULT_TENANT);
      renderPage();
      expect(await screen.findByLabelText("Vault Token")).toHaveAttribute(
        "placeholder",
        "Saved — leave empty to keep it"
      );
      expect(screen.queryByLabelText("Vault Address")).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /save/i }));

      await waitFor(() => expect(captured.body).not.toBeNull());
      expect(captured.body).toMatchObject({ globalVaultAuthMethod: "token" });
      expect(captured.body).not.toHaveProperty("globalVaultCredential");
    });

    it("clears the credential when the global Vault is unticked", async () => {
      setup();
      const captured = capturePatch(GLOBAL_VAULT_TENANT);
      renderPage();
      await userEvent.click(await screen.findByLabelText("Log in to the global Vault"));
      expect(screen.queryByLabelText("Vault Token")).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: /save/i }));

      await waitFor(() => expect(captured.body).not.toBeNull());
      expect(captured.body).toMatchObject({
        globalVaultAuthMethod: null,
        globalVaultCredential: null,
      });
    });

    it("asks for a role id and a new secret id when switching to AppRole", async () => {
      setup();
      const captured = capturePatch(GLOBAL_VAULT_TENANT);
      renderPage();
      await screen.findByLabelText("Vault Token");
      await userEvent.click(screen.getByRole("tab", { name: "AppRole" }));
      await userEvent.click(screen.getByRole("button", { name: /save/i }));

      expect(await screen.findByText("Role ID is required")).toBeInTheDocument();
      expect(screen.getByText("Secret ID is required")).toBeInTheDocument();
      expect(captured.body).toBeNull();

      await userEvent.type(screen.getByLabelText("Vault Role ID"), "role-1");
      await userEvent.type(screen.getByLabelText("Vault Secret ID"), "sid-1");
      await userEvent.click(screen.getByRole("button", { name: /save/i }));
      await waitFor(() => expect(captured.body).not.toBeNull());
      expect(captured.body).toMatchObject({
        globalVaultAuthMethod: "approle",
        globalVaultRoleId: "role-1",
        globalVaultCredential: "sid-1",
      });
    });
  });
});
