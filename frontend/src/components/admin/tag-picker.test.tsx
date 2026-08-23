import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import { TagPicker } from "./tag-picker";

const BASE = "http://localhost:8000";

/** Controlled wrapper so a click's effect on the selection is observable. */
function Harness({ initial = [] as string[], readOnly = false }) {
  const [value, setValue] = useState<string[]>(initial);
  return (
    <>
      <TagPicker value={value} onChange={setValue} readOnly={readOnly} />
      <output data-testid="selection">{value.join(",")}</output>
    </>
  );
}

/** Open the picker's dialog and return its panel. */
async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Select tags…" }));
  return await screen.findByRole("dialog", { name: "Select tags" });
}

describe("TagPicker", () => {
  it("keeps the vocabulary behind a dialog instead of listing it inline", async () => {
    render(<Harness />);

    // The whole point of the dialog: the field's height is the selection's, not
    // the tenant's tag count.
    expect(await screen.findByRole("button", { name: "Select tags…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "aws" })).not.toBeInTheDocument();
  });

  it("offers every tag once the dialog is opened", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const dialog = await openDialog(user);

    expect(within(dialog).getByRole("button", { name: "aws" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "production" })).toBeInTheDocument();
  });

  it("adds a tag to the selection when the dialog's choice is confirmed", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "aws" }));
    await user.click(within(dialog).getByRole("button", { name: "Select" }));

    await waitFor(() => expect(screen.getByTestId("selection")).toHaveTextContent("tag-2"));
  });

  it("leaves the selection untouched when the dialog is cancelled", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "aws" }));
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(screen.getByTestId("selection")).toHaveTextContent("");
  });

  it("shows the current selection as removable chips", async () => {
    render(<Harness initial={["tag-1"]} />);
    expect(await screen.findByRole("button", { name: "Remove production" })).toBeInTheDocument();
  });

  it("shows the tag's description in its chip's tooltip", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["tag-1"]} />);
    await user.hover(await screen.findByText("production"));
    expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent(
      "Live customer-facing environment."
    );
  });

  it("drops a tag when its chip's remove button is pressed", async () => {
    const user = userEvent.setup();
    render(<Harness initial={["tag-1"]} />);
    await user.click(await screen.findByRole("button", { name: "Remove production" }));
    expect(screen.getByTestId("selection")).toHaveTextContent("");
  });

  it("labels an id with no matching tag by the id itself", async () => {
    render(<Harness initial={["tag-gone"]} />);
    // Rendered rather than dropped, so a stale id is never silently discarded.
    expect(await screen.findByRole("button", { name: "Remove tag-gone" })).toBeInTheDocument();
  });

  it("renders read-only chips and no way in when readOnly", async () => {
    render(<Harness initial={["tag-1"]} readOnly />);
    await waitFor(() => expect(screen.getByText("production")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Select tags…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove production" })).not.toBeInTheDocument();
  });

  it("points at the tags admin page instead of opening an empty dialog", async () => {
    server.use(http.get(`${BASE}/api/v1/tags`, () => envelope([])));
    render(<Harness />);

    expect(await screen.findByRole("link", { name: "Create one" })).toHaveAttribute(
      "href",
      "/admin/tags"
    );
    expect(screen.queryByRole("button", { name: "Select tags…" })).not.toBeInTheDocument();
  });
});
