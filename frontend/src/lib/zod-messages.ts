/**
 * @module zod-messages — Keeps the wording of Zod's string-length errors.
 *
 * The admin forms validate against schemas generated from the OpenAPI spec, so
 * their `minLength` / `maxLength` errors show Zod's default text. Zod 4 changed
 * that text to "Too small: expected string to have >=3 characters"; this
 * restores the Zod 3 wording. Every other issue keeps Zod's default.
 *
 * Imported for its side effect by the admin layout and the test setup.
 */
import { z } from "zod";

z.config({
  customError: (issue) => {
    if (issue.origin !== "string") return undefined;
    if (issue.code === "too_small") {
      return `String must contain at least ${issue.minimum} character(s)`;
    }
    if (issue.code === "too_big") {
      return `String must contain at most ${issue.maximum} character(s)`;
    }
    return undefined;
  },
});
