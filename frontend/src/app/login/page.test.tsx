import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
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
      prefetch: vi.fn(),
      refresh: vi.fn(),
    });
    const loginSpy = vi.fn(() => envelope(USER));
    server.use(http.post("http://localhost:8000/api/v1/auth/login", loginSpy));

    render(<LoginPage />);
    await user.type(screen.getByRole("textbox", { name: /username/i }), "alice");
    await user.type(screen.getByLabelText(/password/i), "secret123abc");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(loginSpy).toHaveBeenCalled());
    expect(replaceMock).toHaveBeenCalledWith("/admin");
  });

  it("submits the typed tenant name in the request body", async () => {
    const user = userEvent.setup();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
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
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(requestBody?.tenantName).toBe("acme-corp"));
  });

  it("omits tenantName from the request body when left blank", async () => {
    const user = userEvent.setup();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
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
    await user.click(screen.getByRole("button", { name: /sign in/i }));

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
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Invalid username or password",
        variant: "error",
      })
    );
  });
});
