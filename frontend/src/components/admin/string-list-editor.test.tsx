import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StringListEditor } from "./string-list-editor";

describe("StringListEditor", () => {
  it("renders one labeled input per entry", () => {
    render(<StringListEditor name="args" values={["-y", "pkg"]} onChange={vi.fn()} />);
    expect(screen.getByLabelText("args value 1")).toHaveValue("-y");
    expect(screen.getByLabelText("args value 2")).toHaveValue("pkg");
  });

  it("reports the full list with the edited entry replaced", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<StringListEditor name="args" values={["-y", "pkg"]} onChange={onChange} />);
    await user.type(screen.getByLabelText("args value 2"), "!");
    expect(onChange).toHaveBeenCalledWith(["-y", "pkg!"]);
  });

  it("appends an empty entry when the add button is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <StringListEditor name="args" values={["-y"]} onChange={onChange} addLabel="+ Add argument" />
    );
    await user.click(screen.getByRole("button", { name: "+ Add argument" }));
    expect(onChange).toHaveBeenCalledWith(["-y", ""]);
  });

  it("removes the clicked row", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<StringListEditor name="args" values={["-y", "pkg"]} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Remove args row 1" }));
    expect(onChange).toHaveBeenCalledWith(["pkg"]);
  });

  it("renders only the add button when the list is empty", () => {
    render(<StringListEditor name="args" values={[]} onChange={vi.fn()} />);
    expect(screen.queryByLabelText("args value 1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ Add row" })).toBeInTheDocument();
  });
});
