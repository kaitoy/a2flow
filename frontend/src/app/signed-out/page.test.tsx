import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { render } from "@/test/test-utils";
import SignedOutPage from "./page";

describe("SignedOutPage", () => {
  it("confirms the sign-out and links back to the sign-in page", () => {
    render(<SignedOutPage />);
    expect(screen.getByRole("heading", { name: "You have signed out" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute("href", "/login");
  });
});
