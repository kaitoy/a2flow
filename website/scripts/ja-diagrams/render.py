"""Derive the Japanese manual diagrams from the English diagram-design sources.

Every diagram under ``website/diagram-sources/<section>/`` has a Japanese twin under
``website/diagram-sources/ja/<section>/`` and a light/dark SVG pair under
``website/i18n/ja/docusaurus-plugin-content-docs/current/<section>/img/``. Rather than
hand-editing those, this script rebuilds them from the English light HTML:

1. apply the exact-string replacements listed for the diagram in ``specs.py``
   (translated labels, widened edge-label masks, occasional box geometry);
2. give every ``<text>`` that now contains CJK a Noto Sans JP fallback stack and a
   12px floor, as diagram-design's CJK guidance requires;
3. derive the dark HTML by re-applying the colour substitutions that turn the English
   light file into the English dark file (they differ only by colour tokens and the
   ``-dark`` suffix on the accessible-name ids);
4. export both HTML files to standalone SVGs the way diagram-design's ``export.md`` does.

Run it from anywhere, with no arguments to rebuild every diagram in ``specs.py`` or with
``<section>/<name>`` arguments to rebuild a subset::

    python website/scripts/ja-diagrams/render.py
    python website/scripts/ja-diagrams/render.py guides/secrets-usage

It needs only the standard library. A rough text-fit report is printed per diagram; it
estimates 1em per full-width glyph and flags labels that overrun their box or sit below
12px, so treat it as a hint and confirm in a browser.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specs import SPECS

WEBSITE = Path(__file__).resolve().parents[2]
EN_SRC = WEBSITE / "diagram-sources"
JA_SRC = EN_SRC / "ja"
JA_DOCS = WEBSITE / "i18n" / "ja" / "docusaurus-plugin-content-docs" / "current"

COLOR = re.compile(r"#[0-9a-fA-F]{6}\b|rgba\([^)]*\)")
TEXT = re.compile(r"<text\b([^>]*)>([^<]*)</text>")
JP_SANS = "'Inter', 'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', sans-serif"
FONT_LINK_JA = "&family=Noto+Sans+JP:wght@400;500;600&family=Noto+Sans+KR"
FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1"
    "&amp;family=Inter:wght@400;500;600&amp;family=Geist+Mono:wght@400;500;600"
    "&amp;family=Noto+Sans+JP:wght@400;500;600"
    "&amp;family=Noto+Sans+KR:wght@400;500;600&amp;family=Noto+Serif+KR:wght@400"
    "&amp;family=Noto+Sans+TC:wght@400;500;600&amp;family=Noto+Serif+TC:wght@400&amp;display=swap');"
)

ColorKey = tuple[str, str, str]


def read(path: Path) -> str:
    """Read a UTF-8 text file."""
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    """Write a UTF-8 text file with LF line endings, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def has_cjk(text: str) -> bool:
    """Return whether the text contains any character outside the Latin/punctuation range."""
    return any(ord(c) > 0x2E7F for c in text)


def localize_text(match: re.Match[str]) -> str:
    """Rewrite one ``<text>`` element for Japanese content.

    Latin-only labels are returned unchanged. Labels containing CJK get the Noto Sans JP
    fallback stack, lose ``letter-spacing`` (meaningless on full-width glyphs) and
    ``font-style="italic"`` (Noto Sans JP has no italic face), and are raised to 12px.
    """
    attrs, content = match.group(1), match.group(2)
    if not has_cjk(content):
        return match.group(0)
    attrs = re.sub(r'font-family="[^"]*"', f'font-family="{JP_SANS}"', attrs)
    attrs = re.sub(r'\s*letter-spacing="[^"]*"', "", attrs)
    attrs = re.sub(r'\s*font-style="italic"', "", attrs)
    size = re.search(r'font-size="([\d.]+)"', attrs)
    if size and float(size.group(1)) < 12:
        attrs = attrs.replace(size.group(0), 'font-size="12"')
    return f"<text{attrs}>{content}</text>"


def build_light(name: str) -> None:
    """Write the Japanese light HTML for ``name`` from the English one and its spec.

    Args:
        name: Diagram id as ``<section>/<basename>``, e.g. ``guides/secrets-usage``.

    Raises:
        AssertionError: If a spec's search string does not occur exactly as often as the
            spec says (once by default), which means the English source changed.
    """
    out = read(EN_SRC / f"{name}.html")
    out = out.replace('<html lang="en">', '<html lang="ja">', 1)
    out = out.replace("&family=Noto+Sans+KR", FONT_LINK_JA, 1)
    for old, new, *rest in SPECS[name]:
        want = rest[0] if rest else 1
        found = out.count(old)
        assert found == want, f"{name}: {old!r} found {found} times, expected {want}"
        out = out.replace(old, new)
    out = TEXT.sub(localize_text, out)
    write(JA_SRC / f"{name}.html", out)


def color_keys(src: str) -> list[tuple[ColorKey, re.Match[str]]]:
    """List every colour token in ``src`` with its (element tag, attribute, colour) key.

    The key carries context because one light colour maps to different dark colours on
    different elements (e.g. ``#1c1e21`` is text ink on ``<text>`` but a fill on ``<rect>``).
    """
    out = []
    for match in COLOR.finditer(src):
        before = src[: match.start()]
        tag = re.findall(r"<(\w+)", before)
        attr = re.findall(r"([\w-]+)\s*[=:]\s*\"?\s*$", before[-40:])
        out.append(((tag[-1] if tag else "", attr[-1] if attr else "", match.group(0)), match))
    return out


def color_map(name: str) -> dict[ColorKey, str]:
    """Learn the light→dark colour substitutions from the English pair for ``name``."""
    light = color_keys(read(EN_SRC / f"{name}.html"))
    dark = color_keys(read(EN_SRC / f"{name}-dark.html"))
    assert len(light) == len(dark), f"{name}: en light/dark colour token counts differ"
    mapping: dict[ColorKey, str] = {}
    for (key, _), (_, dark_match) in zip(light, dark):
        if key in mapping and mapping[key] != dark_match.group(0):
            raise SystemExit(f"{name}: ambiguous mapping {key} -> {mapping[key]} / {dark_match.group(0)}")
        mapping[key] = dark_match.group(0)
    return mapping


def build_dark(name: str) -> None:
    """Write the Japanese dark HTML for ``name`` by recolouring the Japanese light HTML."""
    mapping = color_map(name)
    src = read(JA_SRC / f"{name}.html")
    pieces, pos = [], 0
    for key, match in color_keys(src):
        if key not in mapping:
            raise SystemExit(f"{name}: no dark mapping for {key}")
        pieces.append(src[pos : match.start()])
        pieces.append(mapping[key])
        pos = match.end()
    pieces.append(src[pos:])
    out = "".join(pieces)
    ids = re.search(r'aria-labelledby="([\w-]+)-title \1-desc"', out)
    assert ids, f"{name}: aria-labelledby not found"
    base = ids.group(1)
    out = out.replace(f'aria-labelledby="{base}-title {base}-desc"', f'aria-labelledby="{base}-dark-title {base}-dark-desc"')
    out = out.replace(f'id="{base}-title"', f'id="{base}-dark-title"').replace(f'id="{base}-desc"', f'id="{base}-dark-desc"')
    write(JA_SRC / f"{name}-dark.html", out)


def export_svg(html: Path, svg_out: Path) -> None:
    """Extract the first ``<svg>`` of ``html`` as a standalone SVG file.

    Follows diagram-design's ``references/export.md``: inject the Google Fonts ``@import``
    (with ``&`` escaped for XML), rewrite ``rgba()`` fills/strokes to hex plus ``*-opacity``
    for strict SVG 1.1 consumers, and prepend the XML declaration.
    """
    src = read(html)
    match = re.search(r"<svg\b.*?</svg>", src, re.S)
    assert match, f"{html}: no <svg>"
    svg = match.group(0)
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg and "viewBox=" in svg
    style = f"<style>{FONT_IMPORT}</style>"
    if "<defs>" in svg:
        svg = svg.replace("<defs>", f"<defs>{style}", 1)
    else:
        svg = re.sub(r"(<svg\b[^>]*>)", rf"\1<defs>{style}</defs>", svg, count=1)
    svg = re.sub(
        r'(fill|stroke)="rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d*\.?\d+)\s*\)"',
        lambda m: '{0}="#{1:02x}{2:02x}{3:02x}" {0}-opacity="{4}"'.format(
            m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        ),
        svg,
    )
    svg = re.sub(r'(fill|stroke)="transparent"', r'\1="none"', svg)
    write(svg_out, '<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n")


def export_pair(name: str) -> None:
    """Export the Japanese light and dark HTML of ``name`` to the i18n ``img/`` folder."""
    section, base = name.split("/")
    for suffix in ("", "-dark"):
        export_svg(JA_SRC / f"{name}{suffix}.html", JA_DOCS / section / "img" / f"{base}{suffix}.svg")


def estimate_width(text: str, size: float, mono: bool) -> float:
    """Estimate rendered width in px: 1em per full-width glyph, ~0.55em per Latin glyph."""
    total = 0.0
    for ch in text:
        if ord(ch) > 0x2E7F:
            total += 1.0
        elif mono:
            total += 0.6
        elif ch in "iljtfr.,:;'| ":
            total += 0.3
        elif ch.isupper() or ch in "mwMW":
            total += 0.7
        else:
            total += 0.55
    return total * size


def check_fit(name: str) -> None:
    """Print labels in the Japanese light HTML that look too wide for their box or too small."""
    src = read(JA_SRC / f"{name}.html")
    rects = []
    for match in re.finditer(r"<rect\b([^>]*)/?>", src):
        attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', match.group(1)))
        try:
            rects.append((float(attrs["x"]), float(attrs["y"]), float(attrs["width"]), float(attrs["height"])))
        except (KeyError, ValueError):
            pass
    problems = 0
    for match in TEXT.finditer(src):
        attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', match.group(1)))
        text = match.group(2).strip()
        if not text or "x" not in attrs:
            continue
        x, y = float(attrs["x"]), float(attrs["y"])
        size = float(attrs.get("font-size", 14))
        width = estimate_width(text, size, "Mono" in attrs.get("font-family", ""))
        anchor = attrs.get("text-anchor", "start")
        left = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
        right = left + width
        if has_cjk(text) and size < 12:
            print(f"  SMALL {size}px: {text!r}")
            problems += 1
        for rx, ry, rw, rh in rects:  # the first rect enclosing the anchor point is "its" box
            if rx <= x <= rx + rw and ry <= y <= ry + rh and rw >= 24:
                if left < rx + 4 or right > rx + rw - 4:
                    print(f"  OVERFLOW rect({rx:g},{ry:g},{rw:g}x{rh:g}) text [{left:.0f}..{right:.0f}] {text!r}")
                    problems += 1
                break
    print(f"{name}: {problems} fit issue(s)")


def main(names: list[str]) -> None:
    """Rebuild the given diagrams (all of ``SPECS`` when empty)."""
    for name in names or sorted(SPECS):
        build_light(name)
        check_fit(name)
        build_dark(name)
        export_pair(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
