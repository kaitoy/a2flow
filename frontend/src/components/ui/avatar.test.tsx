import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DEFAULT_AVATAR_PALETTE } from "@/lib/avatar-palette";
import { Avatar } from "./avatar";

const USER_NO_AVATAR = {
  id: "user-1",
  username: "alice",
  tenantId: "tenant-1",
  avatarUpdatedAt: null,
  avatarConfig: null,
};
const USER_WITH_AVATAR = {
  id: "user-1",
  username: "alice",
  avatarUpdatedAt: "2026-06-24T00:00:00.000Z",
  avatarConfig: null,
};
const USER_WITH_CONFIG = {
  id: "user-1",
  username: "alice",
  avatarUpdatedAt: null,
  // Deliberately disjoint from DEFAULT_AVATAR_PALETTE so the tests below can
  // tell a saved palette apart from the fallback.
  avatarConfig: { colors: ["#4a3728", "#efefef", "#883311"] },
};

/**
 * Render a user's generated avatar and reduce it to the parts that depend on
 * the seed. The renderer stamps a fresh unique id into the SVG's mask on every
 * render, so raw markup differs even for identical seeds — this drops ids and
 * keeps only the seed-derived geometry and colors.
 */
function seedSignature(user: React.ComponentProps<typeof Avatar>["user"]): string {
  const { container } = render(<Avatar user={user} />);
  return [...container.querySelectorAll("svg *")]
    .map((el) =>
      [
        el.tagName,
        el.getAttribute("fill") ?? "",
        el.getAttribute("transform") ?? "",
        el.getAttribute("d") ?? "",
        el.getAttribute("width") ?? "",
        el.getAttribute("height") ?? "",
      ].join(":")
    )
    .join("|");
}

describe("Avatar", () => {
  it("renders a generated avatar (no img) when there is no uploaded image", () => {
    const { container } = render(<Avatar user={USER_NO_AVATAR} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("renders the uploaded image with a cache-busting URL when one exists", () => {
    render(<Avatar user={USER_WITH_AVATAR} />);
    const img = screen.getByAltText("alice avatar");
    const src = img.getAttribute("src") ?? "";
    expect(src).toContain("/api/v1/users/user-1/avatar");
    expect(src).toContain("?v=");
  });

  it("falls back to the generated avatar when the image fails to load", () => {
    const { container } = render(<Avatar user={USER_WITH_AVATAR} />);
    fireEvent.error(screen.getByAltText("alice avatar"));
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("renders a customized generated avatar (no img) when avatarConfig is set", () => {
    const { container } = render(<Avatar user={USER_WITH_CONFIG} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("draws the generated avatar from the saved palette", () => {
    const { container } = render(<Avatar user={USER_WITH_CONFIG} />);
    const markup = container.innerHTML.toLowerCase();
    const palette = USER_WITH_CONFIG.avatarConfig.colors;
    expect(palette.some((color) => markup.includes(color))).toBe(true);
    // The default palette is not mixed in once the user has saved their own.
    expect(DEFAULT_AVATAR_PALETTE.some((color) => markup.includes(color.toLowerCase()))).toBe(
      false
    );
  });

  it("falls back to the default palette when the user has no avatarConfig", () => {
    const { container } = render(<Avatar user={USER_NO_AVATAR} />);
    const markup = container.innerHTML.toLowerCase();
    expect(DEFAULT_AVATAR_PALETTE.some((color) => markup.includes(color.toLowerCase()))).toBe(true);
  });

  it("seeds the generated avatar per tenant, so one username differs across tenants", () => {
    expect(seedSignature(USER_NO_AVATAR)).not.toBe(
      seedSignature({ ...USER_NO_AVATAR, tenantId: "tenant-2" })
    );
  });

  it("keeps the same avatar for the same user regardless of their id", () => {
    // The seed is tenant + username, never the user id, so an unrelated record
    // change must not reshuffle the face.
    expect(seedSignature(USER_NO_AVATAR)).toBe(seedSignature({ ...USER_NO_AVATAR, id: "user-99" }));
  });

  it("seeds a platform-scoped user from the username alone", () => {
    expect(seedSignature({ ...USER_NO_AVATAR, tenantId: null })).not.toBe(
      seedSignature(USER_NO_AVATAR)
    );
  });

  it("renders a placeholder without an image while the user is loading", () => {
    const { container } = render(<Avatar user={null} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
