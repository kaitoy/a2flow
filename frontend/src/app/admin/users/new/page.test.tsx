import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewUserPage from "./page";

const CREATED_USER = {
  id: "new-user-id",
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

/** Fill every required field of the create form with valid values. */
async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole("textbox", { name: /username/i }), "alice");
  await user.type(screen.getByRole("textbox", { name: /first name/i }), "Alice");
  await user.type(screen.getByRole("textbox", { name: /last name/i }), "Smith");
  await user.type(screen.getByRole("textbox", { name: /email/i }), "alice@example.com");
  await user.type(screen.getByLabelText(/password/i), "secret123abc");
}

describe("NewUserPage", () => {
  it("renders username input", () => {
    render(<NewUserPage />);
    expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
  });

  it("renders enabled and email verified checkboxes", () => {
    render(<NewUserPage />);
    expect(screen.getByRole("checkbox", { name: "Enabled" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Email verified" })).not.toBeChecked();
  });

  it("submits create api on form submit", async () => {
    const user = userEvent.setup();
    const createSpy = vi.fn(() => envelope(CREATED_USER, 201));
    server.use(http.post("http://localhost:8000/api/v1/users", createSpy));

    render(<NewUserPage />);
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

    render(<NewUserPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/users"));
  });

  it("shows validation error on blur when username is empty", async () => {
    const user = userEvent.setup();
    render(<NewUserPage />);
    await user.click(screen.getByRole("textbox", { name: /username/i }));
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 3 character/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when username has invalid characters", async () => {
    const user = userEvent.setup();
    render(<NewUserPage />);
    await user.type(screen.getByRole("textbox", { name: /username/i }), "has space");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid/i)).toBeInTheDocument());
  });

  it("shows validation error on blur when email is invalid", async () => {
    const user = userEvent.setup();
    render(<NewUserPage />);
    await user.type(screen.getByRole("textbox", { name: /email/i }), "not-an-email");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/invalid email/i)).toBeInTheDocument());
  });

  it("shows validation error when password is too short", async () => {
    const user = userEvent.setup();
    render(<NewUserPage />);
    await user.type(screen.getByLabelText(/password/i), "short");
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 12 character/i)).toBeInTheDocument());
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/users", () => new HttpResponse(null, { status: 409 }))
    );

    render(<NewUserPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(screen.getByText(/409/)).toBeInTheDocument());
  });
});
