import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import {
  KeyValueEditor,
  type KeyValuePair,
  pairsToRecord,
  recordToPairs,
} from "./key-value-editor";

/** Controlled host mirroring how a react-hook-form Controller drives the editor. */
function Host({
  initial = [],
  valueType,
}: {
  initial?: KeyValuePair[];
  valueType?: "text" | "password";
}) {
  const [pairs, setPairs] = useState<KeyValuePair[]>(initial);
  return <KeyValueEditor name="headers" pairs={pairs} onChange={setPairs} valueType={valueType} />;
}

describe("pairsToRecord", () => {
  it("drops rows with an empty key and trims the rest", () => {
    expect(
      pairsToRecord([
        { key: " a ", value: "1" },
        { key: "", value: "ignored" },
      ])
    ).toEqual({ a: "1" });
  });

  it("keeps empty values so they can act as a sentinel", () => {
    expect(pairsToRecord([{ key: "a", value: "" }])).toEqual({ a: "" });
  });
});

describe("recordToPairs", () => {
  it("expands a map into rows in iteration order", () => {
    expect(recordToPairs({ a: "1", b: "2" })).toEqual([
      { key: "a", value: "1" },
      { key: "b", value: "2" },
    ]);
  });
});

describe("KeyValueEditor", () => {
  it("renders one labelled row per pair", () => {
    render(<Host initial={[{ key: "Authorization", value: "Bearer x" }]} />);
    expect(screen.getByLabelText("headers key 1")).toHaveValue("Authorization");
    expect(screen.getByLabelText("headers value 1")).toHaveValue("Bearer x");
  });

  it("appends an empty row on add", async () => {
    const user = userEvent.setup();
    render(<Host />);
    await user.click(screen.getByRole("button", { name: /add row/i }));
    expect(screen.getByLabelText("headers key 1")).toHaveValue("");
  });

  it("removes the clicked row", async () => {
    const user = userEvent.setup();
    render(
      <Host
        initial={[
          { key: "a", value: "1" },
          { key: "b", value: "2" },
        ]}
      />
    );
    await user.click(screen.getByRole("button", { name: /remove headers row 1/i }));
    expect(screen.getByLabelText("headers key 1")).toHaveValue("b");
    expect(screen.queryByLabelText("headers key 2")).not.toBeInTheDocument();
  });

  it("edits a row in place", async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ key: "a", value: "" }]} />);
    await user.type(screen.getByLabelText("headers value 1"), "typed");
    expect(screen.getByLabelText("headers value 1")).toHaveValue("typed");
  });

  it("renders plain text values by default", () => {
    render(<Host initial={[{ key: "a", value: "1" }]} />);
    expect(screen.getByLabelText("headers value 1")).toHaveAttribute("type", "text");
  });

  it("masks values when valueType is password", () => {
    render(<Host initial={[{ key: "a", value: "1" }]} valueType="password" />);
    expect(screen.getByLabelText("headers value 1")).toHaveAttribute("type", "password");
  });
});
