import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { ADMIN } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import TenantSettingsPage from "./page";

const BASE = "http://localhost:8000";

function renderPage() {
  return render(<TenantSettingsPage />, { preloadedState: ADMIN });
}

describe("TenantSettingsPage", () => {
  it("prefills the form from the saved settings", async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant-settings`, () =>
        envelope({ loginMaxFailures: 3, loginLockoutMinutes: 45 })
      )
    );
    renderPage();
    expect(await screen.findByRole("heading", { name: "Tenant Settings" })).toBeInTheDocument();
    expect(await screen.findByLabelText(/Failed Sign-ins Before Lockout/)).toHaveValue("3");
    expect(screen.getByLabelText(/Lockout Minutes/)).toHaveValue("45");
  });

  it("saves the edited values as numbers", async () => {
    let captured: unknown = null;
    server.use(
      http.patch(`${BASE}/api/v1/tenant-settings`, async ({ request }) => {
        captured = await request.json();
        return envelope({ loginMaxFailures: 10, loginLockoutMinutes: 30 });
      })
    );
    renderPage();
    const minutes = await screen.findByLabelText(/Lockout Minutes/);
    await userEvent.clear(minutes);
    await userEvent.type(minutes, "30");
    const failures = screen.getByLabelText(/Failed Sign-ins Before Lockout/);
    await userEvent.clear(failures);
    await userEvent.type(failures, "10");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(captured).toMatchObject({ loginMaxFailures: 10, loginLockoutMinutes: 30 })
    );
  });

  it("rejects an out-of-range value without saving", async () => {
    let patched = false;
    server.use(
      http.patch(`${BASE}/api/v1/tenant-settings`, () => {
        patched = true;
        return envelope({ loginMaxFailures: 5, loginLockoutMinutes: 15 });
      })
    );
    renderPage();
    const failures = await screen.findByLabelText(/Failed Sign-ins Before Lockout/);
    await userEvent.clear(failures);
    await userEvent.type(failures, "0");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("Enter a whole number from 1 to 100")).toBeInTheDocument();
    expect(patched).toBe(false);
  });

  it("shows a message when the settings cannot be loaded", async () => {
    server.use(
      http.get(`${BASE}/api/v1/tenant-settings`, () =>
        envelopeErr("FORBIDDEN", "Operation not permitted", 403)
      )
    );
    renderPage();
    expect(await screen.findByText("The tenant settings could not be loaded.")).toBeInTheDocument();
  });

  describe("Vault connection", () => {
    const VAULT_SETTINGS = {
      loginMaxFailures: 5,
      loginLockoutMinutes: 15,
      vaultAddr: "https://vault.acme.example.com",
      vaultAuthMethod: "token",
      vaultRoleId: null,
      vaultApproleMount: null,
      vaultCredentialSet: true,
    };

    /** Serve `settings` and capture the PATCH body the page sends. */
    function capturePatch(settings: object) {
      const captured: { body: Record<string, unknown> | null } = { body: null };
      server.use(
        http.get(`${BASE}/api/v1/tenant-settings`, () => envelope(settings)),
        http.patch(`${BASE}/api/v1/tenant-settings`, async ({ request }) => {
          captured.body = (await request.json()) as Record<string, unknown>;
          return envelope(settings);
        })
      );
      return captured;
    }

    it("keeps a saved token by leaving the field blank", async () => {
      const captured = capturePatch(VAULT_SETTINGS);
      renderPage();
      await screen.findByDisplayValue("https://vault.acme.example.com");
      expect(screen.getByLabelText("Vault Token")).toHaveAttribute(
        "placeholder",
        "Saved — leave empty to keep it"
      );
      await userEvent.click(screen.getByRole("button", { name: /save/i }));

      await waitFor(() => expect(captured.body).not.toBeNull());
      expect(captured.body).toMatchObject({
        vaultAddr: "https://vault.acme.example.com",
        vaultAuthMethod: "token",
      });
      expect(captured.body).not.toHaveProperty("vaultCredential");
    });

    it("clears the whole connection when the address is emptied", async () => {
      const captured = capturePatch(VAULT_SETTINGS);
      renderPage();
      const addr = await screen.findByDisplayValue("https://vault.acme.example.com");
      await userEvent.clear(addr);
      await userEvent.click(screen.getByRole("button", { name: /save/i }));

      await waitFor(() => expect(captured.body).not.toBeNull());
      expect(captured.body).toMatchObject({ vaultAddr: null, vaultCredential: null });
    });

    it("asks for a role id and a new secret id when switching to AppRole", async () => {
      const captured = capturePatch(VAULT_SETTINGS);
      renderPage();
      await screen.findByDisplayValue("https://vault.acme.example.com");
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
        vaultAuthMethod: "approle",
        vaultRoleId: "role-1",
        vaultCredential: "sid-1",
      });
    });
  });
});
