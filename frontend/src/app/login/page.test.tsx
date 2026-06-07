import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
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
  it("renders username and password fields", () => {
    render(<LoginPage />);
    expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("logs in and navigates to the chat on success", async () => {
    const user = userEvent.setup();
    const replaceMock = vi.fn();
    vi.mocked(useRouter).mockReturnValue({
      push: vi.fn(),
      replace: replaceMock,
      back: vi.fn(),
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
    expect(replaceMock).toHaveBeenCalledWith("/new-session");
  });

  it("shows an error message on invalid credentials", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/auth/login", () =>
        HttpResponse.json(
          {
            meta: { requestId: "r", receivedAt: "", respondedAt: "" },
            data: null,
            error: { code: "UNAUTHENTICATED", message: "Invalid", details: null },
          },
          { status: 401 }
        )
      )
    );

    render(<LoginPage />);
    await user.type(screen.getByRole("textbox", { name: /username/i }), "alice");
    await user.type(screen.getByLabelText(/password/i), "wrong-pass-123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/invalid username or password/i)).toBeInTheDocument();
  });
});
