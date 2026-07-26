import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DetailItem, DetailList } from "./detail-list";

describe("DetailList", () => {
  it("renders its items as a definition list", () => {
    const { container } = render(
      <DetailList>
        <DetailItem label="Username" value="alice" />
        <DetailItem label="Email" value="alice@example.com" />
      </DetailList>
    );

    expect(container.querySelector("dl")).toBeInTheDocument();
    expect(container.querySelectorAll("dt")).toHaveLength(2);
    expect(container.querySelectorAll("dd")).toHaveLength(2);
    expect(screen.getByText("Username")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("merges extra classes onto the grid", () => {
    const { container } = render(
      <DetailList className="glass-panel p-4">
        <DetailItem label="Username" value="alice" />
      </DetailList>
    );

    const dl = container.querySelector("dl");
    expect(dl).toHaveClass("grid", "glass-panel", "p-4");
  });

  it("omits the class separator when no extra classes are given", () => {
    const { container } = render(
      <DetailList>
        <DetailItem label="Username" value="alice" />
      </DetailList>
    );

    expect(container.querySelector("dl")?.className).toBe("grid grid-cols-1 sm:grid-cols-2 gap-4");
  });

  it("accepts a node as the item value", () => {
    render(<DetailList>{<DetailItem label="Roles" value={<span>Admin</span>} />}</DetailList>);

    expect(screen.getByText("Admin").tagName).toBe("SPAN");
  });
});
