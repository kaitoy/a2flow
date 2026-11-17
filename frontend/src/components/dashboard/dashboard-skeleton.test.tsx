import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DashboardSkeleton } from "./dashboard-skeleton";

describe("DashboardSkeleton", () => {
  it("holds the place of the five tiles and the four panels", () => {
    const { container } = render(<DashboardSkeleton />);
    expect(container.querySelectorAll(".console-panel")).toHaveLength(9);
    expect(container.querySelector(".skeleton")).not.toBeNull();
  });
});
