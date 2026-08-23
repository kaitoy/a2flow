import { describe, expect, it } from "vitest";
import reducer, { dismissToast, showToast } from "./toastSlice";

describe("toastSlice", () => {
  it("enqueues a toast with a generated id and default success variant", () => {
    const state = reducer(undefined, showToast({ message: "Saved" }));
    expect(state.items).toHaveLength(1);
    expect(state.items[0].message).toBe("Saved");
    expect(state.items[0].variant).toBe("success");
    expect(state.items[0].id).toBeTruthy();
  });

  it("honors an explicit variant", () => {
    const state = reducer(undefined, showToast({ message: "Oops", variant: "error" }));
    expect(state.items[0].variant).toBe("error");
  });

  it("assigns unique ids to successive toasts", () => {
    let state = reducer(undefined, showToast({ message: "first" }));
    state = reducer(state, showToast({ message: "second" }));
    expect(state.items).toHaveLength(2);
    expect(state.items[0].id).not.toBe(state.items[1].id);
  });

  it("removes a toast by id on dismiss", () => {
    const seeded = reducer(undefined, showToast({ message: "bye" }));
    const id = seeded.items[0].id;
    const state = reducer(seeded, dismissToast(id));
    expect(state.items).toHaveLength(0);
  });

  it("ignores dismiss for an unknown id", () => {
    const seeded = reducer(undefined, showToast({ message: "stay" }));
    const state = reducer(seeded, dismissToast("does-not-exist"));
    expect(state.items).toHaveLength(1);
  });

  it("merges a repeated error toast into the existing one instead of stacking a duplicate", () => {
    let state = reducer(undefined, showToast({ message: "Failed to load", variant: "error" }));
    state = reducer(state, showToast({ message: "Failed to load", variant: "error" }));
    state = reducer(state, showToast({ message: "Failed to load", variant: "error" }));
    expect(state.items).toHaveLength(1);
    expect(state.items[0].count).toBe(3);
  });

  it("keeps error toasts with different messages separate", () => {
    let state = reducer(undefined, showToast({ message: "Failed to load", variant: "error" }));
    state = reducer(state, showToast({ message: "Failed to save", variant: "error" }));
    expect(state.items).toHaveLength(2);
    expect(state.items[0].count).toBeUndefined();
    expect(state.items[1].count).toBeUndefined();
  });

  it("does not merge repeated success toasts with the same message", () => {
    let state = reducer(undefined, showToast({ message: "Saved" }));
    state = reducer(state, showToast({ message: "Saved" }));
    expect(state.items).toHaveLength(2);
  });
});
