"""Open Knowledge Format (OKF v0.2) rendering of a knowledge base's pages.

Turns the rows of :class:`models.knowledge.KnowledgePage` into the files of an
`OKF bundle <https://github.com/GoogleCloudPlatform/open-knowledge-format>`_:
one Markdown document with YAML frontmatter per page, and a generated
``index.md`` per directory listing what it holds. The reserved ``index.md``
files are never stored, so they always agree with the pages they list; the
other reserved name, ``log.md``, is not produced.

Links inside a bundle use the absolute form the spec recommends: a path from
the bundle root with a leading ``/`` (``/topics/vpn-setup.md``). The same path
is the page's key in the database, so a link the agent writes is also an
argument it can pass to ``read_knowledge_page``.
"""

import io
import re
import zipfile
from collections.abc import Iterable
from typing import Any, Protocol

import yaml

#: The OKF specification version the generated bundles target.
OKF_VERSION = "0.2"

#: File names OKF reserves at every directory level; never valid page paths.
RESERVED_FILE_NAMES = frozenset({"index.md", "log.md"})

#: A page path: up to three lowercase kebab-case directories, then a
#: kebab-case file name ending in ``.md``.
_PAGE_PATH = re.compile(
    r"^/(?:[a-z0-9][a-z0-9-]{0,62}/){0,3}[a-z0-9][a-z0-9-]{0,99}\.md$"
)


class PageLike(Protocol):
    """The page attributes rendering reads -- satisfied by ``KnowledgePage``."""

    path: str
    type: str
    title: str
    description: str
    body: str
    meta: dict[str, Any]


def normalize_page_path(raw: str) -> str:
    """Validate a page path, adding the leading ``/`` and ``.md`` when missing.

    Args:
        raw: The path as the agent or a client wrote it.

    Returns:
        The canonical path, e.g. ``/topics/vpn-setup.md``.

    Raises:
        ValueError: If the path is not lowercase kebab-case segments, is
            nested more than three directories deep, or names a reserved file.
    """
    path = raw.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.endswith(".md"):
        path = f"{path}.md"
    if path.rsplit("/", 1)[-1] in RESERVED_FILE_NAMES:
        raise ValueError(f"{path!r} is a reserved file name")
    if not _PAGE_PATH.match(path):
        raise ValueError(
            f"{raw!r} is not a valid page path: use lowercase kebab-case "
            "segments, at most three directories deep, e.g. /topics/vpn-setup.md"
        )
    return path


def frontmatter(page: PageLike) -> dict[str, Any]:
    """Return a page's complete OKF frontmatter, in a stable key order."""
    data: dict[str, Any] = {
        "type": page.type,
        "title": page.title,
        "description": page.description,
    }
    for key in ("tags", "generated", "sources"):
        if page.meta.get(key):
            data[key] = page.meta[key]
    for key, value in page.meta.items():
        data.setdefault(key, value)
    return data


def _yaml_block(data: dict[str, Any]) -> str:
    """Render a frontmatter block, delimiters included."""
    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000)
    return f"---\n{dumped}---\n"


def render_page(page: PageLike) -> str:
    """Render one page as the OKF concept document it is in a bundle."""
    return f"{_yaml_block(frontmatter(page))}\n{page.body.strip()}\n"


def _directory_of(path: str) -> str:
    """Return the directory a path lives in, with a trailing ``/`` (``/`` for the root)."""
    return path.rsplit("/", 1)[0] + "/"


def directories(pages: Iterable[PageLike]) -> list[str]:
    """Return every directory that holds a page, directly or below it, sorted."""
    found = {"/"}
    for page in pages:
        parts = page.path.strip("/").split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            found.add("/" + "/".join(parts[:depth]) + "/")
    return sorted(found)


def _heading_for(directory: str) -> str:
    """Return a readable heading for a directory, e.g. ``/how-tos/`` -> ``How tos``."""
    name = directory.strip("/").rsplit("/", 1)[-1]
    return name.replace("-", " ").capitalize()


def render_index(
    pages: Iterable[PageLike],
    directory: str = "/",
    *,
    title: str,
    description: str | None = None,
) -> str:
    """Render the ``index.md`` of one directory of the bundle.

    Lists the pages directly in ``directory`` and the subdirectories below it,
    each as a bulleted link with a short description, the shape the OKF spec
    gives index files. The root index additionally carries the bundle's
    ``okf_version`` frontmatter, the one frontmatter an index may have.

    Args:
        pages: Every page of the knowledge base.
        directory: The directory to index, with leading and trailing ``/``.
        title: Heading of the root index (the knowledge base's name).
        description: Introductory text of the root index.

    Returns:
        The index document. A directory with no pages yields only its heading.
    """
    pages = list(pages)
    directory = "/" + directory.strip("/") + "/" if directory.strip("/") else "/"
    is_root = directory == "/"
    lines: list[str] = []
    if is_root:
        lines.append(_yaml_block({"okf_version": OKF_VERSION}).rstrip("\n"))
        lines.append(f"# {title}")
        if description:
            lines += ["", description.strip()]
    else:
        lines.append(f"# {_heading_for(directory)}")

    here = [p for p in pages if _directory_of(p.path) == directory]
    if here:
        lines += ["", "## Pages", ""]
        for page in sorted(here, key=lambda p: p.title.lower()):
            summary = f" - {page.description}" if page.description else ""
            lines.append(f"* [{page.title}]({page.path}){summary}")

    children = [
        d
        for d in directories(pages)
        if d != directory
        and d.startswith(directory)
        and "/" not in d[len(directory) :].strip("/")
    ]
    if children:
        lines += ["", "## Sections", ""]
        for child in children:
            count = sum(1 for p in pages if p.path.startswith(child))
            noun = "page" if count == 1 else "pages"
            lines.append(f"* [{_heading_for(child)}]({child}index.md) - {count} {noun}")
    return "\n".join(lines) + "\n"


def build_bundle(
    pages: Iterable[PageLike], *, title: str, description: str | None = None
) -> bytes:
    """Package a knowledge base's pages as a zipped OKF bundle.

    Args:
        pages: Every page of the knowledge base.
        title: The knowledge base's name, heading the root index.
        description: The knowledge base's description, under that heading.

    Returns:
        The zip archive's bytes: one file per page at its path, plus an
        ``index.md`` in every directory.
    """
    pages = list(pages)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for directory in directories(pages):
            archive.writestr(
                f"{directory.lstrip('/')}index.md",
                render_index(pages, directory, title=title, description=description),
            )
        for page in pages:
            archive.writestr(page.path.lstrip("/"), render_page(page))
    return buffer.getvalue()
