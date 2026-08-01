import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FormLayout } from "./form-layout";

describe("FormLayout", () => {
  it("renders the header, the main content, and the aside", () => {
    render(
      <FormLayout header={<h1>Edit Thing</h1>} aside={<p>Created at</p>}>
        <form aria-label="Thing" />
      </FormLayout>
    );

    expect(screen.getByRole("heading", { name: "Edit Thing" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Thing" })).toBeInTheDocument();
    expect(screen.getByRole("complementary")).toHaveTextContent("Created at");
  });

  it("omits the aside element when there is nothing to put in it", () => {
    render(
      <FormLayout header={<h1>Edit Thing</h1>}>
        <form aria-label="Thing" />
      </FormLayout>
    );

    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("keeps both column tracks on the grid so the main column does not reflow", () => {
    const { container } = render(
      <FormLayout header={<h1>Edit Thing</h1>}>
        <form aria-label="Thing" />
      </FormLayout>
    );

    const grid = container.querySelector(".grid");
    expect(grid).toHaveClass("@4xl:grid-cols-[minmax(0,1fr)_16rem]");
  });
});
