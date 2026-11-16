import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { render } from "@/test/test-utils";
import { AuthCard } from "./auth-card";

describe("AuthCard", () => {
  it("renders the title and children in a plain card", () => {
    const { container } = render(
      <AuthCard title="Hello">
        <p>Body</p>
      </AuthCard>
    );
    expect(screen.getByRole("heading", { name: "Hello" })).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
    expect(container.querySelector("form")).toBeNull();
  });

  it("renders a form submitting to onSubmit when given one", () => {
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    const { container } = render(
      <AuthCard title="Sign in" onSubmit={onSubmit}>
        <button type="submit">Go</button>
      </AuthCard>
    );
    const form = container.querySelector("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);
    expect(onSubmit).toHaveBeenCalledOnce();
  });
});
