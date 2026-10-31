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
      expect(captured).toEqual({ loginMaxFailures: 10, loginLockoutMinutes: 30 })
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
});
