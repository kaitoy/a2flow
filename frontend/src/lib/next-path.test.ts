import { describe, expect, it } from "vitest";
import { changePasswordPath, loginPath, safeNextPath } from "./next-path";

describe("safeNextPath", () => {
  it.each([
    ["/workflows/w1?x=1", "/workflows/w1?x=1"],
    ["/", "/"],
    [null, "/"],
    [undefined, "/"],
    ["", "/"],
    ["workflows", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["https://evil.example/", "/"],
    ["/a\nb", "/"],
  ])("maps %j to %j", (value, expected) => {
    expect(safeNextPath(value)).toBe(expected);
  });
});

describe("loginPath", () => {
  it("carries the page to return to", () => {
    expect(loginPath("/workflows/w1?x=1")).toBe("/login?next=%2Fworkflows%2Fw1%3Fx%3D1");
  });

  it("is plain /login for the welcome page or an unsafe value", () => {
    expect(loginPath("/")).toBe("/login");
    expect(loginPath("//evil.example")).toBe("/login");
  });
});

describe("changePasswordPath", () => {
  it("carries the page to return to, like loginPath", () => {
    expect(changePasswordPath("/workflows")).toBe("/change-password?next=%2Fworkflows");
    expect(changePasswordPath("/")).toBe("/change-password");
  });
});
