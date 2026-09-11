import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { SkillContentDialog } from "./skill-content-dialog";

vi.mock("@a2ui/markdown-it", () => ({ renderMarkdown: (s: string) => s }));

const CONTENT_URL = "http://localhost:8000/api/v1/agent-skills/:skillId/content";

describe("SkillContentDialog", () => {
  it("fetches and renders the skill's content when opened", async () => {
    server.use(http.get(CONTENT_URL, () => envelope({ content: "Do the thing." })));

    render(<SkillContentDialog open skillId="skill-1" onClose={() => {}} />);

    expect(await screen.findByText("Do the thing.")).toBeInTheDocument();
  });

  it("does not fetch while closed", async () => {
    const spy = vi.fn(() => envelope({ content: "Do the thing." }));
    server.use(http.get(CONTENT_URL, spy));

    render(<SkillContentDialog open={false} skillId="skill-1" onClose={() => {}} />);

    await waitFor(() => expect(spy).not.toHaveBeenCalled());
  });

  it("calls onClose from the Close button", async () => {
    const onClose = vi.fn();
    server.use(http.get(CONTENT_URL, () => envelope({ content: "Do the thing." })));
    render(<SkillContentDialog open skillId="skill-1" onClose={onClose} />);
    await screen.findByText("Do the thing.");

    screen.getByRole("button", { name: /close/i }).click();
    expect(onClose).toHaveBeenCalled();
  });
});
