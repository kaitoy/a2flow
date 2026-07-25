import { describe, expect, it } from "vitest";
import { avatarPalette, DEFAULT_AVATAR_PALETTE } from "./avatar-palette";

describe("avatarPalette", () => {
  it("falls back to the default palette when there is no config", () => {
    expect(avatarPalette(null)).toEqual([...DEFAULT_AVATAR_PALETTE]);
    expect(avatarPalette(undefined)).toEqual([...DEFAULT_AVATAR_PALETTE]);
  });

  it("falls back to the default palette when the saved palette is empty", () => {
    expect(avatarPalette({ colors: [] })).toEqual([...DEFAULT_AVATAR_PALETTE]);
  });

  it("uses the saved palette when one is set", () => {
    expect(avatarPalette({ colors: ["#123456", "#abcdef"] })).toEqual(["#123456", "#abcdef"]);
  });

  it("returns a copy so callers cannot mutate the default palette", () => {
    const palette = avatarPalette(null);
    palette[0] = "#000000";
    expect(DEFAULT_AVATAR_PALETTE[0]).toBe("#16BFA9");
  });
});
