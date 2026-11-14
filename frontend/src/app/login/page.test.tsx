import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API_BASE } from "@/lib/api";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render } from "@/test/test-utils";
import LoginPage from "./page";

const USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: false,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

describe("LoginPage", () => {
  it("renders username, tenant, and password fields", () => {
    render(<LoginPage />);
    expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/tenant/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("logs in and navigates to the welcome page on success", async () => {
    const user = userEvent.setup();
    const replaceMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: replaceMock,
      back: vi.fn(),
      forward: vi.fn(),
      bfcacheId: "",
      prefetch: vi.fn(),
      refresh: vi.fn(),
    });
    const loginSpy = vi.fn(() => envelope(USER));
    server.use(http.post("http://localhost:8000/api/v1/auth/login", loginSpy));

    render(<LoginPage />);
    await user.type(screen.getByRole("textbox", { name: /username/i }), "alice");
    await user.type(screen.getByLabelText(/password/i), "secret123abc");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => expect(loginSpy).toHaveBeenCalled());
    expect(replaceMock).toHaveBeenCalledWith("/");
  });

  it("submits the typed tenant name in the request body", async () => {
    const user = userEvent.setup();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
      bfcacheId: "",
      prefetch: vi.fn(),
      refresh: vi.fn(),
    });
    let requestBody: Record<string, unknown> | undefined;
    server.use(
      http.post("http://localhost:8000/api/v1/auth/login", async ({ request }) => {
        requestBody = (await request.json()) as Record<string, unknown>;
        return envelope(USER);
      })
    );

    render(<LoginPage />);
    await user.type(screen.getByRole("textbox", { name: /username/i }), "alice");
    await user.type(screen.getByLabelText(/tenant/i), "acme-corp");
    await user.type(screen.getByLabelText(/password/i), "secret123abc");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => expect(requestBody?.tenantName).toBe("acme-corp"));
  });

  it("omits tenantName from the request body when left blank", async () => {
    const user = userEvent.setup();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
      bfcacheId: "",
      prefetch: vi.fn(),
      refresh: vi.fn(),
    });
    let requestBody: Record<string, unknown> | undefined;
    server.use(
      http.post("http://localhost:8000/api/v1/auth/login", async ({ request }) => {
        requestBody = (await request.json()) as Record<string, unknown>;
        return envelope(USER);
      })
    );

    render(<LoginPage />);
    await user.type(screen.getByRole("textbox", { name: /username/i }), "alice");
    await user.type(screen.getByLabelText(/password/i), "secret123abc");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() => expect(requestBody).toBeDefined());
    expect(requestBody?.tenantName).toBeUndefined();
  });

  it("shows an error toast on invalid credentials", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/auth/login", () =>
        envelopeErr("UNAUTHENTICATED", "Invalid username or password", 401)
      )
    );

    render(<LoginPage />);
    await user.type(screen.getByRole("textbox", { name: /username/i }), "alice");
    await user.type(screen.getByLabelText(/password/i), "wrong-pass-123");
    await user.click(screen.getByRole("button", { name: /^sign in$/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Invalid username or password",
        variant: "error",
      })
    );
  });

  describe("single sign-on", () => {
    const originalLocation = window.location;
    afterEach(() => {
      Object.defineProperty(window, "location", {
        value: originalLocation,
        writable: true,
        configurable: true,
      });
      window.history.pushState({}, "", "/");
    });

    it("disables the SSO button until a tenant is entered", async () => {
      const user = userEvent.setup();
      render(<LoginPage />);
      const button = screen.getByTestId("login-sso");
      expect(button).toHaveTextContent("Sign in with SSO");
      expect(button).toBeDisabled();

      await user.type(screen.getByLabelText(/tenant/i), "acme");
      expect(button).toBeEnabled();
    });

    it("navigates to the OIDC start route for the typed tenant", async () => {
      const user = userEvent.setup();
      const assign = vi.fn();
      Object.defineProperty(window, "location", {
        value: { ...window.location, assign },
        writable: true,
        configurable: true,
      });
      render(<LoginPage />);
      await user.type(screen.getByLabelText(/tenant/i), " acme ");
      await user.click(screen.getByTestId("login-sso"));

      expect(assign).toHaveBeenCalledWith(`${API_BASE}/api/v1/auth/oidc/start?tenant=acme`);
    });

    it("shows a toast for the sso_error in the query and strips it", async () => {
      const replace = vi.fn();
      vi.mocked(useRouter).mockReturnValue({
        push: vi.fn(),
        replace,
        back: vi.fn(),
        forward: vi.fn(),
        bfcacheId: "",
        prefetch: vi.fn(),
        refresh: vi.fn(),
      });
      window.history.pushState({}, "", "/login?sso_error=not_permitted");
      const { store: pageStore } = render(<LoginPage />);

      await waitFor(() =>
        expect(pageStore.getState().toast.items.at(-1)).toMatchObject({
          message: "Your identity provider account is not allowed to sign in to A2Flow.",
          variant: "error",
        })
      );
      expect(replace).toHaveBeenCalledWith("/login");
    });

    it("falls back to the generic message for an unknown sso_error", async () => {
      window.history.pushState({}, "", "/login?sso_error=bogus");
      const { store: pageStore } = render(<LoginPage />);

      await waitFor(() =>
        expect(pageStore.getState().toast.items.at(-1)).toMatchObject({
          message: "Single sign-on failed. Please try again.",
          variant: "error",
        })
      );
    });
  });
});
