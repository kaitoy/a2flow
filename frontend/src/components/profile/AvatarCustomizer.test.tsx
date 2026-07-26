import { fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { DEFAULT_AVATAR_PALETTE } from "@/lib/avatar-palette";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { AvatarCustomizer } from "./AvatarCustomizer";

beforeAll(() => {
  // jsdom doesn't implement object URLs; the embedded AvatarField uses them for
  // the selected-file preview.
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

describe("AvatarCustomizer", () => {
  it("renders one swatch per palette slot, seeded from the default palette", () => {
    const { container } = render(<AvatarCustomizer user={USER} />);
    expect(screen.getByText("Palette")).toBeInTheDocument();
    const swatches = container.querySelectorAll<HTMLInputElement>('input[type="color"]');
    expect(swatches).toHaveLength(DEFAULT_AVATAR_PALETTE.length);
    // <input type="color"> normalizes its value to lowercase hex.
    expect(swatches[0].value).toBe(DEFAULT_AVATAR_PALETTE[0].toLowerCase());
  });

  it("seeds the swatches from the user's saved palette when there is one", () => {
    const { container } = render(
      <AvatarCustomizer user={{ ...USER, avatarConfig: { colors: ["#112233", "#445566"] } }} />
    );
    const swatches = container.querySelectorAll<HTMLInputElement>('input[type="color"]');
    expect(swatches).toHaveLength(2);
    expect(swatches[0].value).toBe("#112233");
  });

  it("saves the palette when Save is clicked", async () => {
    const captured = capturePatchBody();
    render(<AvatarCustomizer user={USER} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    const config = (captured.current as { avatarConfig: { colors: string[] } }).avatarConfig;
    expect(config.colors).toEqual([...DEFAULT_AVATAR_PALETTE]);
  });

  it("records an edited swatch in the saved palette", async () => {
    const captured = capturePatchBody();
    const { container } = render(<AvatarCustomizer user={USER} />);
    const swatches = container.querySelectorAll<HTMLInputElement>('input[type="color"]');
    fireEvent.input(swatches[1], { target: { value: "#ff00ff" } });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    const config = (captured.current as { avatarConfig: { colors: string[] } }).avatarConfig;
    expect(config.colors[1]).toBe("#ff00ff");
    // Untouched slots keep their seeded value verbatim — only the DOM input
    // normalizes to lowercase, the saved palette does not.
    expect(config.colors[0]).toBe(DEFAULT_AVATAR_PALETTE[0]);
  });

  it("clears the config and restores the default palette when Reset is clicked", async () => {
    const captured = capturePatchBody();
    const { container } = render(
      <AvatarCustomizer user={{ ...USER, avatarConfig: { colors: ["#112233"] } }} />
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    await waitFor(() => expect(captured.current).toBeDefined());
    expect((captured.current as { avatarConfig: unknown }).avatarConfig).toBeNull();
    const swatches = container.querySelectorAll<HTMLInputElement>('input[type="color"]');
    expect(swatches).toHaveLength(DEFAULT_AVATAR_PALETTE.length);
  });

  it("uploads an image and refreshes the auth user so every avatar updates", async () => {
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

    const { container, store } = render(<AvatarCustomizer user={USER} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["image-bytes"], "a.png", { type: "image/png" });
    await userEvent.upload(input, file);
    await userEvent.click(screen.getByRole("button", { name: /^upload$/i }));

    await waitFor(() =>
      expect(store.getState().auth.user?.avatarUpdatedAt).toBe(uploaded.avatarUpdatedAt)
    );
  });
});
