import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Tooltip } from "./tooltip";

describe("Tooltip", () => {
  it("shows the label on hover", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Full text" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>
    );
    await user.hover(screen.getByRole("button", { name: "trigger" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Full text");
  });

  it("attaches no tooltip behavior when disabled", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Full text" delay={0} disabled>
        <button type="button">trigger</button>
      </Tooltip>
    );
    await user.hover(screen.getByRole("button", { name: "trigger" }));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
