import { beforeEach, describe, expect, it } from "vitest";
import { isKeyboardModality, resetInputModality, trackInputModality } from "./input-modality";

beforeEach(() => {
  trackInputModality();
  resetInputModality();
});

describe("input modality", () => {
  it("starts out pointer-ish", () => {
    expect(isKeyboardModality()).toBe(false);
  });

  it("switches to keyboard on a key press", () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));

    expect(isKeyboardModality()).toBe(true);
  });

  it("switches back to pointer on a mouse press", () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    document.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

    expect(isKeyboardModality()).toBe(false);
  });

  it("registers its listeners only once", () => {
    trackInputModality();
    trackInputModality();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));

    expect(isKeyboardModality()).toBe(true);
  });
});
