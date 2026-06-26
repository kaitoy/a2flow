import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Avatar } from "./avatar";

const USER_NO_AVATAR = {
  id: "user-1",
  username: "alice",
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
  avatarConfig: {
    selections: { head: "braids" },
    colors: { hair: "#4A3728" },
    background: "#EFEFEF",
  },
};

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

  it("renders a placeholder without an image while the user is loading", () => {
    const { container } = render(<Avatar user={null} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
