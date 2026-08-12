import userEvent from "@testing-library/user-event";
import { Users } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { AsyncCheckboxPicker, type PickerOption } from "./async-checkbox-picker";

/** Render the picker with a stub loader; extra props override the defaults. */
function renderPicker(
  props: Partial<React.ComponentProps<typeof AsyncCheckboxPicker>> = {},
  options: PickerOption[] = [
    { value: "a", label: "Alpha" },
    { value: "b", label: "Beta" },
  ]
) {
  const onChange = vi.fn();
  render(
    <AsyncCheckboxPicker
      label="Members"
      icon={Users}
      name="memberIds"
      value={[]}
      onChange={onChange}
      load={() => Promise.resolve(options)}
      emptyMessage="Nothing to pick."
      loadingMessage="Fetching…"
      errorMessage="Could not load."
      filterLabel="Filter things"
      {...props}
    />
  );
  return { onChange };
}

/** Build 20 options, comfortably past the filter threshold. */
function manyOptions(): PickerOption[] {
  return Array.from({ length: 20 }, (_, i) => ({
    value: `id-${i}`,
    label: `Option ${i}`,
  }));
}

describe("AsyncCheckboxPicker", () => {
  it("shows the loading message before the options arrive", () => {
    renderPicker();
    expect(screen.getByText("Fetching…")).toBeInTheDocument();
  });

  it("renders a checkbox per loaded option", async () => {
    renderPicker();
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "Alpha" })).toBeInTheDocument()
    );
    expect(screen.getByRole("checkbox", { name: "Beta" })).toBeInTheDocument();
  });

  it("checks the currently selected options", async () => {
    renderPicker({ value: ["b"] });
    await waitFor(() => screen.getByRole("checkbox", { name: "Beta" }));
    expect(screen.getByRole("checkbox", { name: "Beta" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Alpha" })).not.toBeChecked();
  });

  it("reports the next selection when an option is toggled", async () => {
    const { onChange } = renderPicker();
    await waitFor(() => screen.getByRole("checkbox", { name: "Alpha" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Alpha" }));
    expect(onChange).toHaveBeenCalledWith(["a"]);
  });

  it("shows the empty message when the loader returns nothing", async () => {
    renderPicker({}, []);
    await waitFor(() => expect(screen.getByText("Nothing to pick.")).toBeInTheDocument());
  });

  it("offers a retry when loading fails", async () => {
    const load = vi
      .fn()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce([{ value: "a", label: "Alpha" }]);
    renderPicker({ load });
    await waitFor(() => expect(screen.getByText("Could not load.")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "Alpha" })).toBeInTheDocument()
    );
  });

  it("hides the filter box until the list gets long", async () => {
    renderPicker();
    await waitFor(() => screen.getByRole("checkbox", { name: "Alpha" }));
    expect(screen.queryByLabelText("Filter things")).not.toBeInTheDocument();
  });

  it("filters the options once the list is long enough", async () => {
    renderPicker({}, manyOptions());
    await waitFor(() => screen.getByLabelText("Filter things"));
    await userEvent.type(screen.getByLabelText("Filter things"), "Option 12");
    await waitFor(() =>
      expect(screen.queryByRole("checkbox", { name: "Option 1" })).not.toBeInTheDocument()
    );
    expect(screen.getByRole("checkbox", { name: "Option 12" })).toBeInTheDocument();
  });

  it("keeps selected options visible while filtering", async () => {
    // CheckboxGroup derives the next selection from the options it is given, so
    // filtering a selected option out of the list would silently deselect it.
    renderPicker({ value: ["id-3"] }, manyOptions());
    await waitFor(() => screen.getByLabelText("Filter things"));
    await userEvent.type(screen.getByLabelText("Filter things"), "Option 12");
    expect(screen.getByRole("checkbox", { name: "Option 3" })).toBeChecked();
  });

  it("renders the selection as a plain value when read-only", async () => {
    renderPicker({ value: ["a"], readOnly: true });
    await waitFor(() => expect(screen.getByText("Alpha")).toBeInTheDocument());
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("renders a placeholder when read-only with nothing selected", async () => {
    renderPicker({ value: [], readOnly: true });
    await waitFor(() => expect(screen.getByText("—")).toBeInTheDocument());
  });
});
