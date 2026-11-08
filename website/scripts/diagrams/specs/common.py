"""Helpers shared by the per-locale diagram specs in this package.

Each ``specs/<locale>.py`` defines ``SPECS``, mapping a diagram id
(``<section>/<basename>``) to the exact-substring replacements ``render.py`` applies to
the English light HTML. Each entry is ``(old, new)`` or ``(old, new, count)``; ``old`` must
occur exactly ``count`` times (default once), so a change to the English source that
invalidates a translation fails loudly instead of silently shipping a half-translated
diagram.
"""


def mask(x: int, y: int, w: int, new_w: int, fill: str = "#f2f8fc", h: int = 14) -> tuple[str, str]:
    """Resize an edge-label mask rect for a translated label, keeping its centre.

    Args:
        x: The English rect's ``x``.
        y: The English rect's ``y``.
        w: The English rect's ``width``.
        new_w: Width needed by the translated label.
        fill: The rect's fill (light paper by default).
        h: The English rect's ``height`` (12, 13 or 14 in the sources).

    Returns:
        The ``(old, new)`` replacement pair.
    """
    old = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}"/>'
    nx = x + (w - new_w) // 2
    new = f'<rect x="{nx}" y="{y - 1}" width="{new_w}" height="{h + 2}" rx="2" fill="{fill}"/>'
    return old, new


def label(old: str, new: str) -> tuple[str, str]:
    """Replace the content of a ``<text>`` element, matched on ``>old</text>``."""
    return f">{old}</text>", f">{new}</text>"


def head(en_title: str, title: str, en_desc: str, desc: str, page_title: str | None = None, svg_title: str | None = None) -> list[tuple[str, str]]:
    """Translate the page ``<title>``, the ``<h1>``, and the SVG ``<title>``/``<desc>``.

    The page and SVG titles default to the ``<h1>`` text; pass ``page_title`` /
    ``svg_title`` for the few diagrams where they differ.
    """
    return [
        (f"<title>{page_title or en_title}</title>", f"<title>{title}</title>"),
        (f"<h1>{en_title}</h1>", f"<h1>{title}</h1>"),
        (f'-title">{svg_title or en_title}</title>', f'-title">{title}</title>'),
        (f">{en_desc}</desc>", f">{desc}</desc>"),
    ]
