import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { render, screen, waitFor } from "@/test/test-utils";
import { UserMenu } from "./UserMenu";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

/** Build a User fixture with overridable fields. */
function makeUser(overrides: Partial<User> = {}): User {
  return {
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
    ...overrides,
  };
}

/** Render harness wiring a real anchor button to the menu under test. */
function Harness({ user, onClose }: { user: User | null; onClose: () => void }) {
  const ref = useRef<HTMLButtonElement | null>(null);
  return (
    <>
      <button type="button" ref={ref}>
        anchor
      </button>
      <UserMenu anchorRef={ref} open onClose={onClose} user={user} />
    </>
  );
}

describe("UserMenu", () => {
  it("shows the full name and @username when both are present", async () => {
    render(<Harness user={makeUser()} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());
    expect(screen.getByText("@alice")).toBeInTheDocument();
  });

  it("falls back to the username and omits the secondary line when the name is empty", async () => {
    render(<Harness user={makeUser({ firstName: "", lastName: "" })} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("alice")).toBeInTheDocument());
    expect(screen.queryByText("@alice")).not.toBeInTheDocument();
  });

  it("shows a signed-out header but still a logout item when the user is null", async () => {
    render(<Harness user={null} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Not signed in")).toBeInTheDocument());
    expect(screen.getByRole("menuitem", { name: "Log out" })).toBeInTheDocument();
  });

  it("logs out: clears auth, closes, and navigates to /login", async () => {
    const onClose = vi.fn();
    replaceMock.mockClear();
    const user = userEvent.setup();
    const { store } = render(<Harness user={makeUser()} onClose={onClose} />, {
      preloadedState: { auth: { user: makeUser(), status: "authenticated" } },
    });

    await user.click(screen.getByRole("menuitem", { name: "Log out" }));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(onClose).toHaveBeenCalled();
    expect(store.getState().auth.user).toBeNull();
    expect(store.getState().auth.status).toBe("unauthenticated");
  });
});
