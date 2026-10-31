import { describe, expect, it } from "vitest";
import { z } from "zod";
import { render, screen } from "@/test/test-utils";
import {
  SignInLockoutFields,
  signInLockoutShape,
  toSignInLockoutBody,
  toSignInLockoutFormValues,
} from "./sign-in-lockout-fields";

const schema = z.object(signInLockoutShape);

describe("signInLockoutShape", () => {
  it.each([
    ["1", "1"],
    ["100", "1440"],
  ])("accepts %s failures and %s minutes", (loginMaxFailures, loginLockoutMinutes) => {
    expect(schema.safeParse({ loginMaxFailures, loginLockoutMinutes }).success).toBe(true);
  });

  it.each([
    ["0", "15"],
    ["101", "15"],
    ["5", "0"],
    ["5", "1441"],
    ["2.5", "15"],
    ["", "15"],
  ])("rejects %s failures and %s minutes", (loginMaxFailures, loginLockoutMinutes) => {
    expect(schema.safeParse({ loginMaxFailures, loginLockoutMinutes }).success).toBe(false);
  });
});

describe("form value conversion", () => {
  it("falls back to the defaults and round-trips to numbers", () => {
    const values = toSignInLockoutFormValues({});
    expect(values).toEqual({ loginMaxFailures: "5", loginLockoutMinutes: "15" });
    expect(toSignInLockoutBody(values)).toEqual({ loginMaxFailures: 5, loginLockoutMinutes: 15 });
  });
});

describe("SignInLockoutFields", () => {
  it("renders both inputs and their errors", () => {
    render(
      <SignInLockoutFields
        maxFailures={{
          name: "loginMaxFailures",
          onChange: async () => {},
          onBlur: async () => {},
          ref: () => {},
        }}
        lockoutMinutes={{
          name: "loginLockoutMinutes",
          onChange: async () => {},
          onBlur: async () => {},
          ref: () => {},
        }}
        errors={{ loginMaxFailures: "Too many" }}
      />
    );
    expect(screen.getByLabelText(/Failed Sign-ins Before Lockout/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Lockout Minutes/)).toBeInTheDocument();
    expect(screen.getByText("Too many")).toBeInTheDocument();
  });
});
