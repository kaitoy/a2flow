import { describe, expect, it } from "vitest";
import { okfToDisplayMarkdown } from "./okf-display";

describe("okfToDisplayMarkdown", () => {
  it("fences the frontmatter and turns footnotes into citation keys", () => {
    const page =
      "---\ntype: Procedure\ntitle: VPN\n---\n\nPort 443.[^src-1]\n\n[^src-1]: vpn-guide.md\n";
    expect(okfToDisplayMarkdown(page)).toBe(
      "```yaml\ntype: Procedure\ntitle: VPN\n```\n\n\nPort 443. \\[src-1\\]\n\n- \\[src-1\\] vpn-guide.md\n"
    );
  });

  it("unlinks links to other pages of the bundle", () => {
    expect(
      okfToDisplayMarkdown("See [VPN](/procedures/vpn.md) and [docs](https://example.com).")
    ).toBe("See VPN (`/procedures/vpn.md`) and [docs](https://example.com).");
  });

  it("leaves a document without frontmatter alone apart from footnotes", () => {
    expect(okfToDisplayMarkdown("Plain text.")).toBe("Plain text.");
  });
});
