import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { KnowledgeBasePicker } from "./knowledge-base-picker";

describe("KnowledgeBasePicker", () => {
  it("shows the linked knowledge bases as chips", () => {
    render(
      <KnowledgeBasePicker
        value={["kb-1"]}
        onChange={() => {}}
        initialOptions={[{ value: "kb-1", label: "IT" }]}
      />
    );
    expect(screen.getByText("IT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select knowledge bases…" })).toBeInTheDocument();
  });

  it("unlinks a knowledge base from its chip", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <KnowledgeBasePicker
        value={["kb-1"]}
        onChange={onChange}
        initialOptions={[{ value: "kb-1", label: "IT" }]}
      />
    );
    await user.click(screen.getByRole("button", { name: "Remove IT" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("offers no way to change the selection when read-only", () => {
    render(
      <KnowledgeBasePicker
        value={["kb-1"]}
        onChange={() => {}}
        readOnly
        initialOptions={[{ value: "kb-1", label: "IT" }]}
      />
    );
    expect(screen.getByText("IT")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select knowledge bases…" })).toBeNull();
  });
});
