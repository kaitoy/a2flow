import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useParams, useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import EditUserPage from "./page";

const FULL_USER = {
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

function setup() {
  vi.mocked(useParams).mockReturnValue({ userId: "user-1" });
}

describe("EditUserPage", () => {
  it("prefills form with user data", async () => {
    setup();
    render(<EditUserPage />);
    await waitFor(() => expect(screen.getByDisplayValue("alice")).toBeInTheDocument());
    expect(screen.getByDisplayValue("Alice")).toBeInTheDocument();
    expect(screen.getByDisplayValue("alice@example.com")).toBeInTheDocument();
  });

  it("submits update api on form submit", async () => {
    setup();
    const patchSpy = vi.fn(() => envelope(FULL_USER));
    server.use(http.patch("http://localhost:8000/api/v1/users/:userId", patchSpy));

    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(patchSpy).toHaveBeenCalled());
  });

  it("omits password from the request body when left blank", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).not.toHaveProperty("password");
  });

  it("includes password in the request body when provided", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    await userEvent.type(screen.getByLabelText(/password/i), "newsecret456");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).toMatchObject({ password: "newsecret456" });
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

    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admin/users"));
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
    server.use(http.delete("http://localhost:8000/api/v1/users/:userId", deleteSpy));

    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /delete/i }));

    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    expect(pushMock).toHaveBeenCalledWith("/admin/users");
  });

  it("renders username as a read-only field", async () => {
    setup();
    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    expect(screen.getByRole("textbox", { name: /username/i })).toBeDisabled();
  });

  it("omits username from the request body", async () => {
    setup();
    let capturedBody: Record<string, unknown> | null = null;
    server.use(
      http.patch("http://localhost:8000/api/v1/users/:userId", async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return envelope(FULL_USER);
      })
    );

    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    expect(capturedBody).not.toHaveProperty("username");
  });

  it("shows validation error on blur when required field is cleared", async () => {
    setup();
    const user = userEvent.setup();
    render(<EditUserPage />);
    await waitFor(() => screen.getByDisplayValue("alice"));
    const firstNameInput = screen.getByRole("textbox", { name: /first name/i });
    await user.clear(firstNameInput);
    await user.tab();
    await waitFor(() => expect(screen.getByText(/at least 1 character/i)).toBeInTheDocument());
  });

  it("shows error on load failure", async () => {
    setup();
    server.use(
      http.get(
        "http://localhost:8000/api/v1/users/:userId",
        () => new HttpResponse(null, { status: 404 })
      )
    );

    render(<EditUserPage />);
    await waitFor(() => expect(screen.getByText(/404/)).toBeInTheDocument());
  });
});
