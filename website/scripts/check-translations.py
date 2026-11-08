"""Check that every manual translation still has the shape of its English original.

Docusaurus silently falls back to English for a page a locale lacks, and only warns about a
broken anchor, so a build cannot catch a translation that is missing or has drifted. This
compares each page under ``website/i18n/<locale>/docusaurus-plugin-content-docs/current/``
with ``website/docs/``: headings and their ``{#id}``, code fences, table rows, front matter,
cross-page links, images (the SVG exists, and its ``<desc>`` equals the alt text), and bold
that CommonMark would not render. It also compares the UI string files with the Japanese
ones.

It needs only the standard library. Run it from anywhere::

    python website/scripts/check-translations.py                       # every locale
    python website/scripts/check-translations.py es                    # one locale
    python website/scripts/check-translations.py es guides/secrets.md  # some pages of it

It prints each problem and exits 1 if there are any.
"""

from __future__ import annotations

import html
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

WEBSITE = Path(__file__).resolve().parents[1]
EN_DOCS = WEBSITE / "docs"
LOCALES = ("ja", "es", "zh-CN", "ko", "fr")
# Front matter that holds prose; every other key must keep its English value.
TRANSLATED_FRONT_MATTER = {"title", "description", "sidebar_label"}
# A translation this much shorter than the English has probably lost text.
MIN_LENGTH_RATIO = 0.35

HEADING = re.compile(r"^(#{2,6})\s+(.*?)\s*$")
HEADING_ID = re.compile(r"\s*\\?\{#([\w-]+)\\?\}$")
FENCE = re.compile(r"^\s*(```+|~~~+)(.*)$")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
LINK = re.compile(r"(?<!!)\]\(([^)\s]+)\)")
DESC = re.compile(r"<desc\b[^>]*>(.*?)</desc>", re.S)


def split_page(text: str) -> tuple[dict[str, str], list[str], list[str]]:
    """Split a page into front matter, prose lines, and code-fence info strings.

    Args:
        text: The page's source.

    Returns:
        The front matter as raw key/value strings, the lines outside code fences, and the
        info string of each fence (``mermaid``, ``bash``, ...).
    """
    front: dict[str, str] = {}
    lines = text.splitlines()
    if lines and lines[0] == "---":
        end = lines.index("---", 1)
        for line in lines[1:end]:
            key, _, value = line.partition(":")
            front[key.strip()] = value.strip()
        lines = lines[end + 1 :]
    prose: list[str] = []
    fences: list[str] = []
    marker = ""
    for line in lines:
        match = FENCE.match(line)
        if marker:
            if match and match.group(1) == marker and not match.group(2).strip():
                marker = ""
        elif match:
            marker = match.group(1)
            fences.append(match.group(2).strip())
        else:
            prose.append(line)
    return front, prose, fences


def slugify(text: str) -> str:
    """Return the anchor Docusaurus derives from an English heading's text."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").replace("*", "")
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def heading_ids(prose: list[str]) -> list[tuple[int, str | None, str]]:
    """List a page's h2+ headings as ``(level, explicit id, derived slug)``.

    Repeated slugs get the ``-1``, ``-2`` suffixes Docusaurus gives them.
    """
    seen: Counter[str] = Counter()
    out = []
    for line in prose:
        match = HEADING.match(line)
        if not match:
            continue
        text = match.group(2)
        explicit = HEADING_ID.search(text)
        slug = slugify(HEADING_ID.sub("", text))
        derived = f"{slug}-{seen[slug]}" if seen[slug] else slug
        seen[slug] += 1
        out.append((len(match.group(1)), explicit.group(1) if explicit else None, derived))
    return out


def anchors(prose: list[str]) -> set[str]:
    """Return every anchor a page exposes, from its headings or inline ``<a id>`` tags."""
    found = {explicit or slug for _, explicit, slug in heading_ids(prose)}
    found.update(re.findall(r'\bid="([\w-]+)"', "\n".join(prose)))
    return found


def relative_links(prose: list[str]) -> list[str]:
    """Return the page's cross-page and same-page Markdown link targets."""
    targets = LINK.findall("\n".join(prose))
    return [t for t in targets if t.startswith("#") or re.match(r"\.{0,2}/?[^:]*\.mdx?(#|$)", t)]


def is_punctuation(char: str) -> bool:
    """Return whether CommonMark treats ``char`` as punctuation (Unicode P* or S*)."""
    return unicodedata.category(char)[0] in "PS"


def broken_bold(prose: list[str]) -> list[str]:
    """Return the lines whose ``**`` markers CommonMark would print literally.

    An opening ``**`` right before punctuation needs whitespace or punctuation in front of
    it, and a closing one right after punctuation needs them behind it. CJK text, with no
    spaces around its words, hits this constantly.
    """
    broken = []
    # Bold can wrap across lines, so openers and closers pair up per paragraph.
    for paragraph in "\n".join(prose).split("\n\n"):
        text = f" {re.sub(r'`[^`]*`', 'x', paragraph)} "
        for index, match in enumerate(re.finditer(r"\*\*", text)):
            before, after = text[match.start() - 1], text[match.end()]
            inner, outer = (after, before) if index % 2 == 0 else (before, after)
            if is_punctuation(inner) and not outer.isspace() and not is_punctuation(outer):
                broken.append(text[max(match.start() - 30, 0) : match.end() + 30].strip())
                break
    return broken


def check_page(rel: str, tr_docs: Path, en_anchors: dict[str, set[str]]) -> list[str]:
    """Compare one translated page with its English original.

    Args:
        rel: The page's path relative to the docs root, with forward slashes.
        tr_docs: The locale's docs root.
        en_anchors: Each English page's anchors, keyed by relative path.

    Returns:
        The problems found.
    """
    tr_path = tr_docs / rel
    if not tr_path.exists():
        return ["missing page"]
    en_text = (EN_DOCS / rel).read_text(encoding="utf-8")
    tr_text = tr_path.read_text(encoding="utf-8")
    en_front, en_prose, en_fences = split_page(en_text)
    tr_front, tr_prose, tr_fences = split_page(tr_text)
    problems = []

    if b"\r" in tr_path.read_bytes():
        problems.append("CRLF line endings")
    for key in en_front.keys() | tr_front.keys():
        if key not in en_front or key not in tr_front:
            problems.append(f"front matter key {key!r} differs")
        elif key not in TRANSLATED_FRONT_MATTER and en_front[key] != tr_front[key]:
            problems.append(f"front matter {key!r} must stay {en_front[key]!r}")

    en_heads = heading_ids(en_prose)
    tr_heads = heading_ids(tr_prose)
    if [h[0] for h in en_heads] != [h[0] for h in tr_heads]:
        problems.append(f"heading levels differ: {len(en_heads)} in English, {len(tr_heads)} here")
    else:
        for (_, en_explicit, en_slug), (_, tr_explicit, _) in zip(en_heads, tr_heads, strict=True):
            want = en_explicit or en_slug
            if tr_explicit != want:
                problems.append(f"heading needs id {want!r}, has {tr_explicit!r}")
    if rel.endswith(".mdx") and re.search(r"(?<!\\)\{#[\w-]+\}\s*$", "\n".join(tr_prose), re.M):
        problems.append(r"an .mdx heading id must be written \{#id\}")

    if en_fences != tr_fences:
        problems.append(f"code fences differ: {en_fences} in English, {tr_fences} here")
    for line in broken_bold(tr_prose):
        problems.append(f"bold that will not render: {line[:80]}")
    en_rows = sum(line.lstrip().startswith("|") for line in en_prose)
    tr_rows = sum(line.lstrip().startswith("|") for line in tr_prose)
    if en_rows != tr_rows:
        problems.append(f"table rows differ: {en_rows} in English, {tr_rows} here")
    for row, following in zip(tr_prose, tr_prose[1:], strict=False):
        if row.lstrip().startswith("|") and following.strip() and not following.lstrip().startswith("|"):
            problems.append(f"table row split across lines: {following.strip()[:80]}")
    if len(tr_text) < len(en_text) * MIN_LENGTH_RATIO:
        problems.append(f"suspiciously short: {len(tr_text)} chars against {len(en_text)}")

    en_links = Counter(relative_links(en_prose))
    tr_links = Counter(relative_links(tr_prose))
    for target in (en_links - tr_links) + (tr_links - en_links):
        problems.append(f"link differs from English: {target}")
    for target in tr_links:
        path, _, anchor = target.partition("#")
        linked = (Path(rel).parent / path).as_posix() if path else rel
        linked = re.sub(r"[^/]+/\.\./", "", linked).removeprefix("./")
        if linked not in en_anchors:
            problems.append(f"link to a page that does not exist: {target}")
        elif anchor and anchor not in en_anchors[linked] and anchor not in anchors(split_page((tr_docs / linked).read_text(encoding="utf-8"))[1] if (tr_docs / linked).exists() else []):
            problems.append(f"link to an anchor that does not exist: {target}")

    en_images = [src for _, src in IMAGE.findall("\n".join(en_prose))]
    tr_images = IMAGE.findall("\n".join(tr_prose))
    if en_images != [src for _, src in tr_images]:
        problems.append("image references differ from English")
    for alt, src in tr_images:
        svg = (tr_path.parent / src.split("#")[0]).resolve()
        if not svg.exists():
            problems.append(f"image file missing: {src}")
            continue
        desc = DESC.search(svg.read_text(encoding="utf-8"))
        if desc and html.unescape(desc.group(1).strip()) != alt.replace(r"\[", "[").replace(r"\]", "]"):
            problems.append(f"alt text differs from the <desc> of {src}")
    return problems


def check_strings(locale: str) -> list[str]:
    """Compare a locale's UI string files with the Japanese ones, key by key."""
    problems = []
    ja_root = WEBSITE / "i18n" / "ja"
    for ja_file in sorted(p for p in ja_root.rglob("*.json")):
        rel = ja_file.relative_to(ja_root).as_posix()
        tr_file = WEBSITE / "i18n" / locale / rel
        if not tr_file.exists():
            problems.append(f"{rel}: missing")
            continue
        ja_keys = json.loads(ja_file.read_text(encoding="utf-8")).keys()
        tr_keys = json.loads(tr_file.read_text(encoding="utf-8")).keys()
        for key in sorted(ja_keys ^ tr_keys):
            problems.append(f"{rel}: key {key!r} is in only one of ja and {locale}")
    return problems


def main(argv: list[str]) -> int:
    """Check the requested locales and pages.

    Args:
        argv: Optionally a locale, then optionally pages relative to the docs root.

    Returns:
        The process exit code.
    """
    locales = [argv[0]] if argv else list(LOCALES)
    pages = sorted(
        p.relative_to(EN_DOCS).as_posix() for p in EN_DOCS.rglob("*") if p.suffix in {".md", ".mdx"}
    )
    en_anchors = {rel: anchors(split_page((EN_DOCS / rel).read_text(encoding="utf-8"))[1]) for rel in pages}
    total = 0
    for locale in locales:
        tr_docs = WEBSITE / "i18n" / locale / "docusaurus-plugin-content-docs" / "current"
        problems = [] if argv[1:] else check_strings(locale)
        for rel in argv[1:] or pages:
            problems += [f"{rel}: {problem}" for problem in check_page(rel, tr_docs, en_anchors)]
        if not argv[1:]:
            extra = {p.relative_to(tr_docs).as_posix() for p in tr_docs.rglob("*") if p.suffix in {".md", ".mdx"}} - set(pages)
            problems += [f"{rel}: not in the English docs" for rel in sorted(extra)]
        for problem in problems:
            print(f"{locale} {problem}")
        print(f"{locale}: {len(problems)} problem(s)")
        total += len(problems)
    return 1 if total else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
