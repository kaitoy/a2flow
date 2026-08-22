import { fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { DEFAULT_AVATAR_PALETTE } from "@/lib/avatar-palette";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { AvatarDialog } from "./AvatarDialog";

beforeAll(() => {
  // The embedded AvatarField turns the picked file into an object URL for the
  // selected-file preview; pin it to a fixed value so the src is assertable.
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

const USER = {
  id: "user-1",
  username: "alice",
  firstName: "Alice",
  lastName: "Smith",
  email: "alice@example.com",
  enabled: true,
  emailVerified: false,
  avatarUpdatedAt: null,
  avatarConfig: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
};

const PATCH_URL = "http://localhost:8000/api/v1/users/:userId";

/** Override the PATCH handler to capture the request body. */
function capturePatchBody(): { current: unknown } {
  const captured: { current: unknown } = { current: undefined };
  server.use(
    http.patch(PATCH_URL, async ({ request }) => {
      captured.current = await request.json();
      return HttpResponse.json({
        meta: { requestId: "r", receivedAt: "", respondedAt: "" },
        data: USER,
        error: null,
      });
    })
  );
  return captured;
}

/**
 * The dialog portals to `document.body`, so its controls live outside the
 * render container — every query below goes through `baseElement` or `screen`.
 */
function colorSwatches(baseElement: HTMLElement): NodeListOf<HTMLInputElement> {
  return baseElement.querySelectorAll<HTMLInputElement>('input[type="color"]');
}

describe("AvatarDialog", () => {
  it("renders nothing while closed", () => {
    render(<AvatarDialog open={false} onClose={vi.fn()} user={USER} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders as a labelled modal when open", () => {
    render(<AvatarDialog open onClose={vi.fn()} user={USER} />);
    expect(screen.getByRole("dialog", { name: "Edit avatar" })).toBeInTheDocument();
  });

  it("closes when Close is clicked", async () => {
    const onClose = vi.fn();
    render(<AvatarDialog open onClose={onClose} user={USER} />);
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("renders one swatch per palette slot, seeded from the default palette", () => {
    const { baseElement } = render(<AvatarDialog open onClose={vi.fn()} user={USER} />);
    expect(screen.getByText("Palette")).toBeInTheDocument();
    const swatches = colorSwatches(baseElement);
    expect(swatches).toHaveLength(DEFAULT_AVATAR_PALETTE.length);
    // <input type="color"> normalizes its value to lowercase hex.
    expect(swatches[0].value).toBe(DEFAULT_AVATAR_PALETTE[0].toLowerCase());
  });

  it("seeds the swatches from the user's saved palette when there is one", () => {
    const { baseElement } = render(
      <AvatarDialog
        open
        onClose={vi.fn()}
        user={{ ...USER, avatarConfig: { colors: ["#112233", "#445566"] } }}
      />
    );
    const swatches = colorSwatches(baseElement);
    expect(swatches).toHaveLength(2);
    expect(swatches[0].value).toBe("#112233");
  });

  it("records an edited swatch in the saved palette", async () => {
    const captured = capturePatchBody();
    const { baseElement } = render(<AvatarDialog open onClose={vi.fn()} user={USER} />);
    fireEvent.input(colorSwatches(baseElement)[1], { target: { value: "#ff00ff" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    const config = (captured.current as { avatarConfig: { colors: string[] } }).avatarConfig;
    expect(config.colors[1]).toBe("#ff00ff");
    // Untouched slots keep their seeded value verbatim — only the DOM input
    // normalizes to lowercase, the saved palette does not.
    expect(config.colors[0]).toBe(DEFAULT_AVATAR_PALETTE[0]);
  });

  it("closes the dialog once the palette is saved, rather than celebrating in place", async () => {
    capturePatchBody();
    const onClose = vi.fn();
    const { baseElement } = render(<AvatarDialog open onClose={onClose} user={USER} />);
    fireEvent.input(colorSwatches(baseElement)[1], { target: { value: "#ff00ff" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(screen.queryByRole("button", { name: /saved!/i })).toBeNull();
  });

  it("stores a palette identical to the default as no palette at all", async () => {
    const captured = capturePatchBody();
    render(
      <AvatarDialog
        open
        onClose={vi.fn()}
        user={{ ...USER, avatarConfig: { colors: ["#112233"] } }}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    expect((captured.current as { avatarConfig: unknown }).avatarConfig).toBeNull();
  });

  it("rewinds the swatches on Reset without sending anything", async () => {
    const captured = capturePatchBody();
    const { baseElement } = render(
      <AvatarDialog
        open
        onClose={vi.fn()}
        user={{ ...USER, avatarConfig: { colors: ["#112233"] } }}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset to default" }));

    const swatches = colorSwatches(baseElement);
    expect(swatches).toHaveLength(DEFAULT_AVATAR_PALETTE.length);
    expect(swatches[0].value).toBe(DEFAULT_AVATAR_PALETTE[0].toLowerCase());
    // Nothing reaches the server until Save.
    expect(captured.current).toBeUndefined();
  });

  it("re-seeds the palette from the stored config when reopened, discarding unsaved edits", async () => {
    const onClose = vi.fn();
    const user = { ...USER, avatarConfig: { colors: ["#112233", "#445566"] } };
    const { baseElement, rerender } = render(<AvatarDialog open onClose={onClose} user={user} />);
    fireEvent.input(colorSwatches(baseElement)[0], { target: { value: "#ff00ff" } });
    expect(colorSwatches(baseElement)[0].value).toBe("#ff00ff");

    rerender(<AvatarDialog open={false} onClose={onClose} user={user} />);
    rerender(<AvatarDialog open onClose={onClose} user={user} />);

    await waitFor(() => expect(colorSwatches(baseElement)[0].value).toBe("#112233"));
  });

  it("labels the upload field 'Uploaded image' so it doesn't repeat the dialog title", () => {
    render(<AvatarDialog open onClose={vi.fn()} user={USER} />);
    expect(screen.getByText("Uploaded image")).toBeInTheDocument();
  });

  it("uploads an image, refreshes the auth user, and closes the dialog", async () => {
    const uploaded = { ...USER, avatarUpdatedAt: "2026-06-25T00:00:00.000Z" };
    server.use(
      http.put("http://localhost:8000/api/v1/users/:userId/avatar", () =>
        HttpResponse.json({
          meta: { requestId: "r", receivedAt: "", respondedAt: "" },
          data: uploaded,
          error: null,
        })
      )
    );

    const onClose = vi.fn();
    const { baseElement, store } = render(<AvatarDialog open onClose={onClose} user={USER} />);
    const input = baseElement.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["image-bytes"], "a.png", { type: "image/png" });
    await userEvent.upload(input, file);
    await userEvent.click(screen.getByRole("button", { name: /^upload$/i }));

    await waitFor(() =>
      expect(store.getState().auth.user?.avatarUpdatedAt).toBe(uploaded.avatarUpdatedAt)
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(screen.queryByRole("button", { name: /uploaded!/i })).toBeNull();
  });
});
