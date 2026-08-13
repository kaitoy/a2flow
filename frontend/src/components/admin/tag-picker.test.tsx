import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
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

/** Replace the tag list with `count` generated tags. */
function serveTags(count: number) {
  server.use(
    http.get(`${BASE}/api/v1/tags`, () =>
      envelope(
        Array.from({ length: count }, (_, i) => ({
          id: `tag-${i}`,
          tenantId: "tenant-1",
          name: `tag-${i}`,
          color: "mint",
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
          createdBy: "",
          updatedBy: "",
        }))
      )
    )
  );
}

describe("TagPicker", () => {
  it("offers every tag once loaded", async () => {
    render(<Harness />);
    expect(await screen.findByRole("checkbox", { name: "aws" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "production" })).toBeInTheDocument();
  });

  it("adds a tag to the selection when its checkbox is ticked", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(await screen.findByRole("checkbox", { name: "aws" }));
    expect(screen.getByTestId("selection")).toHaveTextContent("tag-2");
  });

  it("shows the current selection as removable chips", async () => {
    render(<Harness initial={["tag-1"]} />);
    expect(await screen.findByRole("button", { name: "Remove production" })).toBeInTheDocument();
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

  it("renders read-only chips and no checkboxes when readOnly", async () => {
    render(<Harness initial={["tag-1"]} readOnly />);
    await waitFor(() => expect(screen.getByText("production")).toBeInTheDocument());
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove production" })).not.toBeInTheDocument();
  });

  it("points at the tags admin page when no tags exist", async () => {
    server.use(http.get(`${BASE}/api/v1/tags`, () => envelope([])));
    render(<Harness />);
    expect(await screen.findByRole("link", { name: "Create one" })).toHaveAttribute(
      "href",
      "/admin/tags"
    );
  });

  it("offers no filter box for a short vocabulary", async () => {
    render(<Harness />);
    await screen.findByRole("checkbox", { name: "aws" });
    expect(screen.queryByLabelText("Filter tags")).not.toBeInTheDocument();
  });

  it("offers a filter box once the vocabulary gets long", async () => {
    serveTags(13);
    render(<Harness />);
    expect(await screen.findByLabelText("Filter tags")).toBeInTheDocument();
  });

  it("narrows the options to the filter while keeping selected tags visible", async () => {
    const user = userEvent.setup();
    serveTags(13);
    render(<Harness initial={["tag-0"]} />);
    await user.type(await screen.findByLabelText("Filter tags"), "tag-12");

    await waitFor(() =>
      expect(screen.queryByRole("checkbox", { name: "tag-5" })).not.toBeInTheDocument()
    );
    expect(screen.getByRole("checkbox", { name: "tag-12" })).toBeInTheDocument();
    // Kept: CheckboxGroup derives the next selection from the options it is
    // given, so filtering a selected tag out would silently deselect it.
    expect(screen.getByRole("checkbox", { name: "tag-0" })).toBeInTheDocument();
  });
});
