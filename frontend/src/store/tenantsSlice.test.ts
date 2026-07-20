import { describe, expect, it } from "vitest";
import reducer, { tenantsChanged } from "./tenantsSlice";

describe("tenantsSlice", () => {
  it("starts at version 0", () => {
    expect(reducer(undefined, { type: "@@INIT" }).version).toBe(0);
  });

  it("increments the version on each tenantsChanged dispatch", () => {
    const first = reducer(undefined, tenantsChanged());
    expect(first.version).toBe(1);
    const second = reducer(first, tenantsChanged());
    expect(second.version).toBe(2);
  });
});
