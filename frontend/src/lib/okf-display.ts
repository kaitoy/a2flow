/**
 * @module okf-display — Prepares an Open Knowledge Format page for the
 * Markdown renderer, which knows neither YAML frontmatter nor footnotes.
 */

/**
 * Rewrite an OKF page so it renders legibly as plain Markdown.
 *
 * - The YAML frontmatter becomes a fenced `yaml` code block; left as is, the
 *   renderer reads its `---` delimiters as headings and rules.
 * - Links to other pages (`[VPN](/procedures/vpn.md)`) become the title plus the
 *   path in code: the path names a page of the bundle, not a route of this app.
 * - Footnote references (`[^src-1a2b]`) become bracketed citation keys, and
 *   footnote definitions (`[^src-1a2b]: Manual`) a list of sources; the
 *   renderer would otherwise swallow the definitions as link references.
 *
 * @param content - The page as an OKF document.
 * @returns Markdown to hand to the renderer.
 */
export function okfToDisplayMarkdown(content: string): string {
  let body = content;
  let front = "";
  const match = /^---\n([\s\S]*?)\n---\n?/.exec(content);
  if (match) {
    front = `\`\`\`yaml\n${match[1]}\n\`\`\`\n\n`;
    body = content.slice(match[0].length);
  }
  body = body
    .replace(
      /\[([^\]]+)\]\((\/[^)\s]+\.md)\)/g,
      (_, text: string, path: string) => `${text} (\`${path}\`)`
    )
    .replace(
      /^\[\^([^\]]+)\]:\s*(.*)$/gm,
      (_, key: string, text: string) => `- \\[${key}\\] ${text}`
    )
    .replace(/\[\^([^\]]+)\]/g, (_, key: string) => ` \\[${key}\\]`);
  return front + body;
}
