import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import { fireEvent, render, screen, waitFor } from "@/test/test-utils";
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
  const [open, setOpen] = useState(true);
  const ref = useRef<HTMLButtonElement | null>(null);
  return (
    <>
      {/* autoFocus simulates the anchor already holding focus from the click
          that opens the menu in real usage, which the a11y hook needs in
          order to capture it as the element to restore focus to on close. */}
      {/* biome-ignore lint/a11y/noAutofocus: test-only, simulates a pre-focused trigger */}
      <button type="button" ref={ref} autoFocus>
        anchor
      </button>
      <button type="button">outside</button>
      <UserMenu
        anchorRef={ref}
        open={open}
        onClose={() => {
          setOpen(false);
          onClose();
        }}
        user={user}
      />
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

  it("moves focus into the menu when it opens", async () => {
    render(<Harness user={makeUser()} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Account" })).toHaveFocus());
  });

  it("closes and returns focus to the anchor on Escape", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Harness user={makeUser()} onClose={onClose} />);
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Account" })).toHaveFocus());

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("anchor")).toHaveFocus());
  });

  it("closes on an outside pointerdown and returns focus to the anchor", async () => {
    const onClose = vi.fn();
    render(<Harness user={makeUser()} onClose={onClose} />);
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Account" })).toHaveFocus());

    fireEvent.pointerDown(document.body);

    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(screen.getByText("anchor")).toHaveFocus());
  });

  it("wraps Tab from the last item back to the first", async () => {
    const user = userEvent.setup();
    render(<Harness user={makeUser()} onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Account" })).toHaveFocus());

    await user.tab();
    expect(screen.getByRole("menuitem", { name: "Log out" })).toHaveFocus();
    await user.tab();

    expect(screen.getByRole("menuitem", { name: "Account" })).toHaveFocus();
  });
});
