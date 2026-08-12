import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen } from "@/test/test-utils";
import { GroupPicker } from "./group-picker";

const BASE = "http://localhost:8000";

describe("GroupPicker", () => {
  it("shows a chip for each group the user belongs to", async () => {
    render(<GroupPicker value={["group-1"]} onChange={vi.fn()} />);
    expect(await screen.findByText("Developers")).toBeInTheDocument();
  });

  it("lists the tenant's groups in the dialog", async () => {
    const user = userEvent.setup();
    render(<GroupPicker value={[]} onChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Select groups…" }));

    expect(await screen.findByRole("checkbox", { name: "Developers" })).toBeInTheDocument();
  });

  it("assigns the groups checked in the dialog", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<GroupPicker value={[]} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Select groups…" }));
    await user.click(await screen.findByRole("checkbox", { name: "Developers" }));
    await user.click(screen.getByRole("button", { name: "Assign" }));

    expect(onChange).toHaveBeenCalledWith(["group-1"]);
  });

  it("shows an empty message when the tenant has no groups", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/api/v1/user-groups`, () => envelope([])));
    render(<GroupPicker value={[]} onChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Select groups…" }));

    expect(await screen.findByText("This tenant has no user groups yet.")).toBeInTheDocument();
  });

  it("offers neither removal nor selection when read-only", async () => {
    render(<GroupPicker value={["group-1"]} onChange={vi.fn()} readOnly />);

    expect(await screen.findByText("Developers")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select groups…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
  });
});
