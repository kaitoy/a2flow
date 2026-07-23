import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { RootState } from "@/store";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewUserPage from "./page";

/** Build a preloaded auth slice for a signed-in super admin acting as a given tenant. */
function superAdminState(selectedTenantId: string | null): Partial<RootState> {
  return {
    auth: {
      user: { id: "u1", roles: ["super_admin"] } as User,
      status: "authenticated",
      selectedTenantId,
    },
  };
}

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

  it("does not render a tenant field for a non-super-admin viewer", () => {
    render(<NewUserPage />);
    expect(screen.queryByLabelText("Tenant")).not.toBeInTheDocument();
  });

  it("does not render a tenant field for a super-admin viewer either", () => {
    render(<NewUserPage />, { preloadedState: superAdminState("tenant-1") });
    expect(screen.queryByLabelText("Tenant")).not.toBeInTheDocument();
  });

  it("submits the app-bar selected tenant for a super-admin viewer", async () => {
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> | undefined;
    server.use(
      http.post("http://localhost:8000/api/v1/users", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope(CREATED_USER, 201);
      })
    );

    render(<NewUserPage />, { preloadedState: superAdminState("tenant-1") });
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(receivedBody?.tenantId).toBe("tenant-1"));
  });

  it("submits a null tenantId when granting super_admin, regardless of the app-bar selection", async () => {
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> | undefined;
    server.use(
      http.post("http://localhost:8000/api/v1/users", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope(CREATED_USER, 201);
      })
    );

    render(<NewUserPage />, { preloadedState: superAdminState("tenant-1") });
    await fillRequiredFields(user);
    await user.click(screen.getByRole("checkbox", { name: "Super Admin" }));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(receivedBody?.tenantId).toBeNull());
    expect(receivedBody?.roles).toEqual(["super_admin"]);
  });

  it("disables save and shows a hint when no tenant is selected in the app bar", async () => {
    const user = userEvent.setup();
    render(<NewUserPage />, { preloadedState: superAdminState(null) });
    await fillRequiredFields(user);

    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
    expect(
      screen.getByText(/select a tenant in the header before creating this user/i)
    ).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Super Admin" }));

    expect(screen.getByRole("button", { name: /save/i })).not.toBeDisabled();
    expect(
      screen.queryByText(/select a tenant in the header before creating this user/i)
    ).not.toBeInTheDocument();
  });

  it("does not block save for a non-super-admin viewer, and submits a null tenantId", async () => {
    const user = userEvent.setup();
    let receivedBody: Record<string, unknown> | undefined;
    server.use(
      http.post("http://localhost:8000/api/v1/users", async ({ request }) => {
        receivedBody = (await request.json()) as Record<string, unknown>;
        return envelope(CREATED_USER, 201);
      })
    );

    render(<NewUserPage />);
    await fillRequiredFields(user);
    expect(screen.getByRole("button", { name: /save/i })).not.toBeDisabled();
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(receivedBody?.tenantId).toBeNull());
  });

  it("shows error on api failure", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("http://localhost:8000/api/v1/users", () =>
        envelopeErr("CONFLICT_UNIQUE", "Username already in use", 409)
      )
    );

    render(<NewUserPage />);
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Username already in use",
        variant: "error",
      })
    );
  });
});
