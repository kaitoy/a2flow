import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@/test/test-utils";
import { MarkdownContentDialog } from "./markdown-content-dialog";

vi.mock("@a2ui/markdown-it", () => ({ renderMarkdown: (s: string) => `<p>${s}</p>` }));

describe("MarkdownContentDialog", () => {
  it("loads and renders the document under the given title when opened", async () => {
    const load = vi.fn(async () => "Hello");
    render(<MarkdownContentDialog open title="Page" panelId="p" load={load} onClose={() => {}} />);
    expect(await screen.findByText("Hello")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Page" })).toBeInTheDocument();
    expect(load).toHaveBeenCalledOnce();
  });

  it("does not load while closed", async () => {
    const load = vi.fn(async () => "Hello");
    render(
      <MarkdownContentDialog open={false} title="Page" panelId="p" load={load} onClose={() => {}} />
    );
    await waitFor(() => expect(load).not.toHaveBeenCalled());
  });
});
