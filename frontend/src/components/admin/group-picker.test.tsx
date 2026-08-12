import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { GroupPicker } from "./group-picker";

const BASE = "http://localhost:8000";

describe("GroupPicker", () => {
  it("labels each group by name", async () => {
    render(<GroupPicker value={[]} onChange={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "Developers" })).toBeInTheDocument()
    );
  });

  it("checks the groups the user already belongs to", async () => {
    render(<GroupPicker value={["group-1"]} onChange={vi.fn()} />);
    await waitFor(() => screen.getByRole("checkbox", { name: "Developers" }));
    expect(screen.getByRole("checkbox", { name: "Developers" })).toBeChecked();
  });

  it("shows an empty message when the tenant has no groups", async () => {
    server.use(http.get(`${BASE}/api/v1/user-groups`, () => envelope([])));
    render(<GroupPicker value={[]} onChange={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText("This tenant has no user groups yet.")).toBeInTheDocument()
    );
  });

  it("renders the membership as a plain value when read-only", async () => {
    render(<GroupPicker value={["group-1"]} onChange={vi.fn()} readOnly />);
    await waitFor(() => expect(screen.getByText("Developers")).toBeInTheDocument());
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
