import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { SUPER_ADMIN } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import SystemSettingsPage from "./page";

const BASE = "http://localhost:8000";

const CONFIGURED = {
  id: "00000000-0000-0000-0000-000000000001",
  appBaseUrl: "https://a2flow.example.com",
  smtpEnabled: true,
  smtpHost: "smtp.example.com",
  smtpPort: 2525,
  smtpSecurity: "starttls",
  smtpUsername: "mailer",
  smtpFromEmail: "a2flow@example.com",
  smtpFromName: "A2Flow",
  smtpPasswordSet: true,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

function renderPage() {
  return render(<SystemSettingsPage />, { preloadedState: SUPER_ADMIN });
}

/** Serve the fully configured record instead of the handler's blank default. */
function serveConfigured() {
  server.use(http.get(`${BASE}/api/v1/system-settings`, () => envelope(CONFIGURED)));
}

describe("SystemSettingsPage", () => {
  it("titles the page", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "System Settings" })).toBeInTheDocument();
  });

  it("prefills the form from the saved settings", async () => {
    serveConfigured();
    renderPage();
    await waitFor(() => expect(screen.getByDisplayValue("smtp.example.com")).toBeInTheDocument());
    expect(screen.getByDisplayValue("2525")).toBeInTheDocument();
    expect(screen.getByDisplayValue("mailer")).toBeInTheDocument();
    expect(screen.getByDisplayValue("a2flow@example.com")).toBeInTheDocument();
    expect(screen.getByDisplayValue("https://a2flow.example.com")).toBeInTheDocument();
  });

  it("leaves the password field blank and marks it as already saved", async () => {
    serveConfigured();
    renderPage();
    const field = await screen.findByLabelText(/smtp password/i);
    expect(field).toHaveValue("");
    expect(field).toHaveAttribute("placeholder", expect.stringContaining("Saved"));
  });

  it("omits the password from the body when it is left blank", async () => {
    serveConfigured();
    let body: Record<string, unknown> | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/system-settings`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return envelope(CONFIGURED);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body).not.toHaveProperty("smtpPassword");
    expect(body).toMatchObject({
      smtpEnabled: true,
      smtpHost: "smtp.example.com",
      smtpPort: 2525,
      smtpSecurity: "starttls",
      smtpFromEmail: "a2flow@example.com",
    });
  });

  it("sends the password when one is typed", async () => {
    serveConfigured();
    let body: Record<string, unknown> | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/system-settings`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return envelope(CONFIGURED);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.type(screen.getByLabelText(/smtp password/i), "hunter2hunter2");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body?.smtpPassword).toBe("hunter2hunter2");
  });

  it("sends cleared text fields as null so clearing one actually clears it", async () => {
    serveConfigured();
    let body: Record<string, unknown> | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/system-settings`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return envelope(CONFIGURED);
      })
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("A2Flow"));
    await userEvent.clear(screen.getByLabelText(/from name/i));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body?.smtpFromName).toBeNull();
  });

  it("blocks the save when delivery is enabled without a host", async () => {
    const patchSpy = vi.fn(() => envelope(CONFIGURED));
    server.use(http.patch(`${BASE}/api/v1/system-settings`, patchSpy));

    renderPage();
    await waitFor(() => screen.getByLabelText(/smtp host/i));
    await userEvent.click(screen.getByLabelText(/send notifications by email/i));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/host is required/i)).toBeInTheDocument();
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("blocks the save on an out-of-range port", async () => {
    const patchSpy = vi.fn(() => envelope(CONFIGURED));
    server.use(http.patch(`${BASE}/api/v1/system-settings`, patchSpy));

    renderPage();
    const port = await screen.findByLabelText(/smtp port/i);
    await userEvent.clear(port);
    await userEvent.type(port, "70000");
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(await screen.findByText(/between 1 and 65535/i)).toBeInTheDocument();
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("shows a success toast after saving", async () => {
    serveConfigured();
    // The page's own toasts go through the react-redux context, so they land in
    // the render's store -- unlike api.ts's failure toasts, which dispatch to
    // the global singleton.
    const { store: pageStore } = renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(pageStore.getState().toast.items.at(-1)?.message).toBe("System settings updated")
    );
  });

  it("sends a test email through the dedicated endpoint", async () => {
    serveConfigured();
    const testSpy = vi.fn(() => envelope(null));
    server.use(http.post(`${BASE}/api/v1/system-settings/smtp/test`, testSpy));

    const { store: pageStore } = renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.click(screen.getByRole("button", { name: /send test email/i }));

    await waitFor(() => expect(testSpy).toHaveBeenCalled());
    await waitFor(() =>
      expect(pageStore.getState().toast.items.at(-1)?.message).toBe("Test email sent")
    );
  });

  it("does not claim success when the relay rejects the test message", async () => {
    serveConfigured();
    server.use(
      http.post(`${BASE}/api/v1/system-settings/smtp/test`, () =>
        envelopeErr("EMAIL_SEND_FAILED", "Failed to send", 502)
      )
    );

    renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.click(screen.getByRole("button", { name: /send test email/i }));

    await waitFor(() => expect(store.getState().toast.items.at(-1)?.variant).toBe("error"));
    expect(store.getState().toast.items.at(-1)?.message).not.toBe("Test email sent");
  });

  it("explains itself instead of rendering an empty form when the fetch fails", async () => {
    server.use(
      http.get(`${BASE}/api/v1/system-settings`, () =>
        envelopeErr("FORBIDDEN", "Requires one of the roles: super_admin", 403)
      )
    );

    renderPage();
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/smtp host/i)).not.toBeInTheDocument();
  });

  it("opens a confirmation dialog before clearing SMTP settings", async () => {
    serveConfigured();
    const patchSpy = vi.fn(() => envelope(CONFIGURED));
    server.use(http.patch(`${BASE}/api/v1/system-settings`, patchSpy));

    renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.click(screen.getByRole("button", { name: /clear smtp settings/i }));

    expect(await screen.findByRole("dialog", { name: /clear smtp settings/i })).toBeInTheDocument();
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("does not submit when the clear confirmation is cancelled", async () => {
    serveConfigured();
    const patchSpy = vi.fn(() => envelope(CONFIGURED));
    server.use(http.patch(`${BASE}/api/v1/system-settings`, patchSpy));

    renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.click(screen.getByRole("button", { name: /clear smtp settings/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(patchSpy).not.toHaveBeenCalled();
  });

  it("clears every SMTP field and disables delivery on confirm, leaving the base URL alone", async () => {
    serveConfigured();
    let body: Record<string, unknown> | undefined;
    server.use(
      http.patch(`${BASE}/api/v1/system-settings`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return envelope({
          ...CONFIGURED,
          smtpEnabled: false,
          smtpHost: null,
          smtpPort: 587,
          smtpSecurity: "starttls",
          smtpUsername: null,
          smtpFromEmail: null,
          smtpFromName: null,
          smtpPasswordSet: false,
        });
      })
    );

    const { store: pageStore } = renderPage();
    await waitFor(() => screen.getByDisplayValue("smtp.example.com"));
    await userEvent.click(screen.getByRole("button", { name: /clear smtp settings/i }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /^clear$/i }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body).toEqual({
      smtpEnabled: false,
      smtpHost: null,
      smtpPort: 587,
      smtpSecurity: "starttls",
      smtpUsername: null,
      smtpPassword: null,
      smtpFromEmail: null,
      smtpFromName: null,
    });

    await waitFor(() => expect(screen.queryByDisplayValue("smtp.example.com")).toBeNull());
    expect(screen.getByDisplayValue("https://a2flow.example.com")).toBeInTheDocument();
    const passwordField = screen.getByLabelText(/smtp password/i);
    expect(passwordField).not.toHaveAttribute("placeholder", expect.stringContaining("Saved"));
    await waitFor(() =>
      expect(pageStore.getState().toast.items.at(-1)?.message).toBe("SMTP settings cleared")
    );
  });
});
