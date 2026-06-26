import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("renders children", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  it("default type is button", () => {
    render(<Button>x</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("primary variant applies gradient background", () => {
    render(<Button variant="primary">x</Button>);
    expect(screen.getByRole("button").className).toContain("from-accent");
  });

  it("secondary variant applies glass-panel", () => {
    render(<Button variant="secondary">x</Button>);
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("glass-panel");
  });

  it("ghost variant (default) has transparent background", () => {
    render(<Button>x</Button>);
    expect(screen.getByRole("button").className).toContain("bg-transparent");
  });

  it("disabled prop disables the button", () => {
    render(<Button disabled>x</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("onClick fires when clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>x</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("className prop is applied", () => {
    render(<Button className="w-full">x</Button>);
    expect(screen.getByRole("button").className).toContain("w-full");
  });

  it("className does not remove variant classes", () => {
    render(
      <Button variant="primary" className="w-full">
        x
      </Button>
    );
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("from-accent");
    expect(cls).toContain("w-full");
  });

  describe("status labels", () => {
    it("idle status shows the children label", () => {
      render(
        <Button status="idle" pendingLabel="Saving…" doneLabel="Saved!">
          Save
        </Button>
      );
      expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    });

    it("pending status shows the pending label", () => {
      render(
        <Button status="pending" pendingLabel="Saving…" doneLabel="Saved!">
          Save
        </Button>
      );
      expect(screen.getByRole("button", { name: "Saving…" })).toBeInTheDocument();
    });

    it("done status shows the done label", () => {
      render(
        <Button status="done" pendingLabel="Saving…" doneLabel="Saved!">
          Save
        </Button>
      );
      expect(screen.getByRole("button", { name: "Saved!" })).toBeInTheDocument();
    });

    it("done status disables the button and applies the success style", () => {
      render(
        <Button status="done" pendingLabel="Saving…" doneLabel="Saved!">
          Save
        </Button>
      );
      const button = screen.getByRole("button", { name: "Saved!" });
      expect(button).toBeDisabled();
      expect(button.className).toContain("bg-success");
      expect(button.className).toContain("animate-wiggle");
    });

    it("pending status disables the button", () => {
      render(
        <Button status="pending" pendingLabel="Saving…" doneLabel="Saved!">
          Save
        </Button>
      );
      expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    });

    it("idle status leaves the button enabled", () => {
      render(
        <Button status="idle" pendingLabel="Saving…" doneLabel="Saved!">
          Save
        </Button>
      );
      expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    });

    it("reserves width with hidden, aria-hidden copies of every label", () => {
      render(
        <Button status="pending" pendingLabel="Saving…" doneLabel="Saved!">
          Save
        </Button>
      );
      // The idle and done labels stay in the DOM (as width-reservation sizers)
      // but are hidden from the accessible name, so only "Saving…" is exposed.
      const button = screen.getByRole("button", { name: "Saving…" });
      expect(button.textContent).toContain("Save");
      expect(button.textContent).toContain("Saved!");
    });
  });
});
