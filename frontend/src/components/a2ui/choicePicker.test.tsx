import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { customChoicePicker } from "./choicePicker";
import { SurfaceResolvedContext } from "./surfaceResolvedContext";

interface TestChoicePickerProps {
  value?: string[];
  variant?: string;
  displayStyle?: string;
  options?: { label: string; value: string }[];
  setValue: (v: string[]) => void;
  filterable?: boolean;
  label?: string;
}

// See button.test.tsx for why `createComponentImplementation` is mocked to
// expose the render function directly instead of driving the full `@a2ui/web_core` binder.
vi.mock("@a2ui/react/v0_9", () => ({
  createComponentImplementation: (
    _api: unknown,
    RenderComponent: (p: {
      props: TestChoicePickerProps;
      context: { componentModel: { id: string } };
    }) => unknown
  ) => ({ render: RenderComponent }),
}));

const Render = customChoicePicker.render as unknown as (p: {
  props: TestChoicePickerProps;
  context: { componentModel: { id: string } };
}) => ReactNode;

const options = [
  { label: "Cat", value: "cat" },
  { label: "Dog", value: "dog" },
];

// One over DROPDOWN_OPTION_THRESHOLD, so single-choice pickers collapse to a dropdown.
const manyOptions = [
  { label: "t3.micro", value: "t3.micro" },
  { label: "t3.small", value: "t3.small" },
  { label: "t3.medium", value: "t3.medium" },
  { label: "m5.large", value: "m5.large" },
  { label: "m5.xlarge", value: "m5.xlarge" },
  { label: "c5.large", value: "c5.large" },
];

describe("customChoicePicker", () => {
  it("toggles a selection when the surface is not resolved", async () => {
    const setValue = vi.fn();
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{ value: [], variant: "mutuallyExclusive", options, setValue }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );
    const radio = screen.getByRole("radio", { name: "Cat" });
    expect(radio).not.toBeDisabled();
    await userEvent.click(radio);
    expect(setValue).toHaveBeenCalledWith(["cat"]);
  });

  it("is inert and never calls setValue when the surface is resolved", async () => {
    const setValue = vi.fn();
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render
          props={{ value: [], variant: "mutuallyExclusive", options, setValue }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );
    const radio = screen.getByRole("radio", { name: "Cat" });
    expect(radio).toBeDisabled();
    await userEvent.click(radio);
    expect(setValue).not.toHaveBeenCalled();
  });

  it("disables chip-style options too", () => {
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render
          props={{ value: [], displayStyle: "chips", options, setValue: vi.fn() }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );
    expect(screen.getByRole("button", { name: "Cat" })).toBeDisabled();
  });

  it("renders a dropdown for a single choice among many options", () => {
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{
            value: [],
            variant: "mutuallyExclusive",
            options: manyOptions,
            setValue: vi.fn(),
          }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );

    expect(screen.getByRole("combobox")).toHaveTextContent("Select an option");
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("keeps radio buttons when a single choice has few options", () => {
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{ value: [], variant: "mutuallyExclusive", options, setValue: vi.fn() }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );

    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("keeps chips when many options are explicitly styled as chips", () => {
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{
            value: [],
            variant: "mutuallyExclusive",
            displayStyle: "chips",
            options: manyOptions,
            setValue: vi.fn(),
          }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );

    expect(screen.getByRole("button", { name: "t3.micro" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("keeps checkboxes for a multi-select with many options", () => {
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{
            value: [],
            variant: "multipleSelection",
            options: manyOptions,
            setValue: vi.fn(),
          }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );

    expect(screen.getAllByRole("checkbox")).toHaveLength(manyOptions.length);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("selects a dropdown option as a single-element value array", async () => {
    const setValue = vi.fn();
    const user = userEvent.setup();
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{
            value: [],
            variant: "mutuallyExclusive",
            options: manyOptions,
            setValue,
            label: "Instance type",
          }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );

    await user.click(screen.getByRole("combobox", { name: "Instance type" }));
    await user.click(screen.getByRole("option", { name: "m5.large" }));

    expect(setValue).toHaveBeenCalledWith(["m5.large"]);
  });

  it("keeps the selected option listed even when the filter hides it", async () => {
    const user = userEvent.setup();
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{
            value: ["c5.large"],
            variant: "mutuallyExclusive",
            options: manyOptions,
            filterable: true,
            setValue: vi.fn(),
          }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );

    await user.type(screen.getByPlaceholderText("Filter options..."), "t3");

    const trigger = screen.getByRole("combobox");
    expect(trigger).toHaveTextContent("c5.large");
    await user.click(trigger);
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "c5.large" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "t3.micro" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "m5.large" })).not.toBeInTheDocument();
  });

  it("disables the dropdown when the surface is resolved", async () => {
    const user = userEvent.setup();
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render
          props={{
            value: ["t3.micro"],
            variant: "mutuallyExclusive",
            options: manyOptions,
            setValue: vi.fn(),
          }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );

    const trigger = screen.getByRole("combobox");
    expect(trigger).toBeDisabled();
    await user.click(trigger);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
