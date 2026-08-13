import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { TagColor } from "@/lib/api";
import { render, screen } from "@/test/test-utils";
import { TagColorField } from "./tag-color-field";

/** Controlled wrapper so a pick's effect on the value is observable. */
function Harness({ initial = "slate" as TagColor, previewLabel = "" }) {
  const [value, setValue] = useState<TagColor>(initial);
  return (
    <>
      <TagColorField value={value} onChange={setValue} previewLabel={previewLabel} />
      <output data-testid="value">{value}</output>
    </>
  );
}

describe("TagColorField", () => {
  it("offers every palette slot", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("combobox", { name: "Color" }));
    expect(await screen.findByRole("option", { name: "Mint" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Slate" })).toBeInTheDocument();
  });

  it("reports the picked slot", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("combobox", { name: "Color" }));
    await user.click(await screen.findByRole("option", { name: "Amber" }));
    expect(screen.getByTestId("value")).toHaveTextContent("amber");
  });

  it("previews the tag under its current name", () => {
    render(<Harness previewLabel="production" />);
    expect(screen.getByText("production")).toBeInTheDocument();
  });

  it("stands in with a placeholder before a name is typed", () => {
    render(<Harness previewLabel="   " />);
    expect(screen.getByText("tag")).toBeInTheDocument();
  });

  it("names the slot instead of offering a select when readOnly", () => {
    render(<TagColorField value="violet" onChange={vi.fn()} readOnly />);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("Violet")).toBeInTheDocument();
  });
});
