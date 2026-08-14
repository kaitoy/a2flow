import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Tag, TagColor } from "@/lib/api";
import { TagPickerDialog } from "./tag-picker-dialog";

/** Build a tag with the audit fields every `Tag` carries. */
function tag(id: string, name: string, color: TagColor): Tag {
  return {
    id,
    tenantId: "tenant-1",
    name,
    color,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

const TAGS: Tag[] = [
  tag("t-prod", "production", "rose"),
  tag("t-stage", "staging", "rose"),
  tag("t-aws", "aws", "amber"),
  tag("t-db", "database", "indigo"),
];

/** Wraps the dialog with a real trigger so the closed→open transition is testable. */
function Harness({
  initial = [] as string[],
  onAssign = vi.fn(),
}: {
  initial?: string[];
  onAssign?: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      <TagPickerDialog
        open={open}
        onClose={() => setOpen(false)}
        onAssign={onAssign}
        panelId="tag-picker-dialog"
        value={initial}
        tags={TAGS}
      />
    </>
  );
}

/** Open the dialog and return its panel. */
async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "open" }));
  return await screen.findByRole("dialog", { name: "Select tags" });
}

describe("TagPickerDialog", () => {
  it("offers every tag as a toggle chip", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const dialog = await openDialog(user);

    for (const name of ["production", "staging", "aws", "database"]) {
      expect(within(dialog).getByRole("button", { name })).toHaveAttribute("aria-pressed", "false");
    }
  });

  it("marks the tags already attached as pressed", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["t-aws"]} />);

    const dialog = await openDialog(user);

    expect(within(dialog).getByRole("button", { name: "aws" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(within(dialog).getByText("1 selected")).toBeInTheDocument();
  });

  it("narrows the grid to the name query", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const dialog = await openDialog(user);

    await user.type(within(dialog).getByLabelText("Filter tags"), "sta");

    await waitFor(() =>
      expect(within(dialog).queryByRole("button", { name: "production" })).not.toBeInTheDocument()
    );
    expect(within(dialog).getByRole("button", { name: "staging" })).toBeInTheDocument();
  });

  it("narrows the grid to the pressed color swatches", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Rose" }));

    await waitFor(() =>
      expect(within(dialog).queryByRole("button", { name: "aws" })).not.toBeInTheDocument()
    );
    expect(within(dialog).getByRole("button", { name: "production" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "staging" })).toBeInTheDocument();

    // Multi-select: a second swatch widens the result rather than replacing it.
    await user.click(within(dialog).getByRole("button", { name: "Amber" }));
    expect(await within(dialog).findByRole("button", { name: "aws" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "database" })).not.toBeInTheDocument();
  });

  it("clears the color narrowing when the last swatch is pressed off", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const dialog = await openDialog(user);

    const rose = within(dialog).getByRole("button", { name: "Rose" });
    await user.click(rose);
    await waitFor(() => expect(rose).toHaveAttribute("aria-pressed", "true"));
    await user.click(rose);

    // No explicit "All" option — every swatch off is the cleared state.
    expect(await within(dialog).findByRole("button", { name: "aws" })).toBeInTheDocument();
    expect(rose).toHaveAttribute("aria-pressed", "false");
  });

  it("applies the name query and the color filter together", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Rose" }));
    await user.type(within(dialog).getByLabelText("Filter tags"), "s");

    await waitFor(() =>
      expect(within(dialog).queryByRole("button", { name: "database" })).not.toBeInTheDocument()
    );
    // "database" matches the query but not the color; "production" the color
    // but not the query.
    expect(within(dialog).queryByRole("button", { name: "production" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "staging" })).toBeInTheDocument();
  });

  it("says so when nothing matches", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const dialog = await openDialog(user);

    await user.type(within(dialog).getByLabelText("Filter tags"), "nothing");

    expect(await within(dialog).findByText("No tags match the filter.")).toBeInTheDocument();
  });

  it("keeps a selection the filter hides", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "production" }));
    const filter = within(dialog).getByLabelText("Filter tags");
    await user.type(filter, "aws");
    await waitFor(() =>
      expect(within(dialog).queryByRole("button", { name: "production" })).not.toBeInTheDocument()
    );

    // The draft is its own state, not derived from the rendered options, so
    // filtering a selected tag out of view cannot silently deselect it.
    expect(within(dialog).getByText("1 selected")).toBeInTheDocument();
    await user.clear(filter);
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "production" })).toHaveAttribute(
        "aria-pressed",
        "true"
      )
    );
  });

  it("reports the draft on Select", async () => {
    const onAssign = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={["t-aws"]} onAssign={onAssign} />);
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "production" }));
    await user.click(within(dialog).getByRole("button", { name: "Select" }));

    expect(onAssign).toHaveBeenCalledWith(["t-aws", "t-prod"]);
  });

  it("drops a pressed tag from the draft when pressed again", async () => {
    const onAssign = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={["t-aws"]} onAssign={onAssign} />);
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "aws" }));
    await user.click(within(dialog).getByRole("button", { name: "Select" }));

    expect(onAssign).toHaveBeenCalledWith([]);
  });

  it("discards the draft and the filters on Cancel", async () => {
    const onAssign = vi.fn();
    const user = userEvent.setup();
    render(<Harness initial={["t-aws"]} onAssign={onAssign} />);

    const dialog = await openDialog(user);
    await user.type(within(dialog).getByLabelText("Filter tags"), "prod");
    await user.click(await within(dialog).findByRole("button", { name: "production" }));
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    const reopened = await openDialog(user);
    await waitFor(() => expect(within(reopened).getByText("1 selected")).toBeInTheDocument());
    expect(within(reopened).getByLabelText("Filter tags")).toHaveValue("");
    expect(within(reopened).getByRole("button", { name: "production" })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
    expect(onAssign).not.toHaveBeenCalled();
  });
});
