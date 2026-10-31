import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("replaces images with their alt text so they are never fetched", async () => {
    const html = await renderMarkdown("see ![secret](https://evil.example/p?d=x)");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("evil.example");
    expect(html).toContain("secret");
  });

  it("keeps the rest of the markup", async () => {
    expect(await renderMarkdown("**bold**")).toContain("<strong>bold</strong>");
  });
});
