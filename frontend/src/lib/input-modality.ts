/** @module input-modality — Tracks whether the user is currently driving the UI by keyboard or by pointer. */

/**
 * Whether the most recent user interaction came from the keyboard.
 *
 * Starts as `false`: until the user does something, treat focus as pointer-ish
 * and stay quiet.
 */
let keyboardModality = false;

/**
 * Whether the user's last interaction was a key press rather than a pointer
 * press.
 *
 * This is the same distinction the CSS `:focus-visible` pseudo-class draws, and
 * it exists as a module because the headless DOMs used in tests don't model
 * `:focus-visible` faithfully — a component that asks the selector directly
 * cannot be tested.
 *
 * Use it to decide whether focus landing on an element deserves visible
 * feedback. Focus that follows a click, or that a dialog restores to its
 * trigger on close, should not trigger the same affordances keyboard
 * navigation does.
 */
export function isKeyboardModality(): boolean {
  return keyboardModality;
}

/**
 * Starts tracking input modality on the document.
 *
 * Idempotent and safe to call from every component that needs it; the
 * listeners are registered once. Capturing listeners, so a handler that stops
 * propagation cannot hide the interaction from us.
 */
export function trackInputModality(): void {
  if (typeof document === "undefined" || tracking) return;
  tracking = true;
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("pointerdown", onPointerDown, true);
  // Not every environment synthesises pointer events; mousedown/touchstart
  // keep the pointer case honest where they are all that arrives.
  document.addEventListener("mousedown", onPointerDown, true);
  document.addEventListener("touchstart", onPointerDown, true);
}

let tracking = false;

function onKeyDown(): void {
  keyboardModality = true;
}

function onPointerDown(): void {
  keyboardModality = false;
}

/** Resets the tracked modality. Intended for tests. */
export function resetInputModality(): void {
  keyboardModality = false;
}
