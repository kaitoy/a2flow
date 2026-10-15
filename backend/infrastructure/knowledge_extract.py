"""Fetching and text extraction for knowledge sources.

A knowledge source reaches the ingest agent as Markdown: an uploaded PDF, Word
document, HTML page, or text file -- or a web page fetched from its URL -- is
converted by `MarkItDown <https://github.com/microsoft/markitdown>`_, which
keeps headings, lists, and tables, the structure the agent needs to tell
topics apart. Conversion is CPU-bound and synchronous, so it runs in a worker
thread.

Fetching a URL follows the same SSRF rules as every other outbound request
this app makes to a user-supplied address: the URL passed the
:func:`infrastructure.url_safety.assert_public_http_url` check when it was
registered, and each hop -- the first request and every redirect, which is
followed by hand for exactly this reason -- is checked again right before
connecting.
"""

import asyncio
import io
from dataclasses import dataclass
from email.message import Message
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlsplit

import httpx
from markitdown import MarkItDown, StreamInfo

from infrastructure.url_safety import assert_public_http_url

#: File extensions accepted for upload, i.e. the formats the converter reads
#: without optional extras beyond the ``pdf`` and ``docx`` ones installed.
SUPPORTED_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".json"}
)

#: How many redirects one fetch follows before giving up.
_MAX_REDIRECTS = 5

#: Sent with every fetch, so a site operator can tell what is reading the page.
_USER_AGENT = "A2Flow knowledge ingest (+https://kaitoy.github.io/a2flow/)"


class KnowledgeFetchError(Exception):
    """Raised when a source URL cannot be fetched or is too large."""


@dataclass(frozen=True)
class FetchedDocument:
    """The raw bytes of a fetched web page and how the server described them."""

    data: bytes
    content_type: str | None
    url: str


@dataclass(frozen=True)
class ExtractedDocument:
    """A source converted to Markdown."""

    markdown: str
    title: str | None


def is_supported_file(file_name: str) -> bool:
    """Return whether an upload's extension is one the converter reads."""
    return PurePosixPath(file_name.lower()).suffix in SUPPORTED_EXTENSIONS


async def fetch_url(
    url: str,
    *,
    max_bytes: int,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchedDocument:
    """Download a web page, re-checking every hop against the SSRF rules.

    Args:
        url: The page to fetch.
        max_bytes: Largest body accepted; a larger one is abandoned mid-stream.
        timeout: Per-request timeout, in seconds.
        transport: HTTP transport to send through; the network by default
            (tests pass a mock).

    Returns:
        The page's bytes, its ``Content-Type``, and the URL it was served from.

    Raises:
        UnsafeUrlError: If a hop resolves to a non-public address.
        KnowledgeFetchError: On a non-2xx answer, too many redirects, or a
            body over ``max_bytes``.
        httpx.HTTPError: On a network failure.
    """
    current = url
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT},
        transport=transport,
    ) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            await asyncio.to_thread(assert_public_http_url, current)
            async with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise KnowledgeFetchError(f"{current} redirected nowhere")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise KnowledgeFetchError(
                        f"{current} answered HTTP {response.status_code}"
                    )
                buffer = bytearray()
                async for chunk in response.aiter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > max_bytes:
                        raise KnowledgeFetchError(
                            f"{current} is larger than {max_bytes} bytes"
                        )
                return FetchedDocument(
                    bytes(buffer), response.headers.get("content-type"), current
                )
    raise KnowledgeFetchError(f"{url} redirected more than {_MAX_REDIRECTS} times")


def _stream_info(
    file_name: str | None, content_type: str | None, url: str | None
) -> StreamInfo:
    """Describe a document to the converter from its name, media type, and URL."""
    mimetype = charset = None
    if content_type:
        header = Message()
        header["content-type"] = content_type
        mimetype = header.get_content_type()
        charset = header.get_content_charset()
    name = file_name or (PurePosixPath(urlsplit(url).path).name if url else "")
    extension = PurePosixPath(name.lower()).suffix or None
    return StreamInfo(
        mimetype=mimetype,
        charset=charset,
        extension=extension,
        filename=file_name,
        url=url,
    )


def _convert(data: bytes, info: StreamInfo) -> ExtractedDocument:
    """Run the converter; synchronous, for :func:`asyncio.to_thread`."""
    result = MarkItDown(enable_plugins=False).convert_stream(
        io.BytesIO(data), stream_info=info
    )
    return ExtractedDocument(markdown=result.markdown.strip(), title=result.title)


async def extract_markdown(
    data: bytes,
    *,
    file_name: str | None = None,
    content_type: str | None = None,
    url: str | None = None,
) -> ExtractedDocument:
    """Convert a document to Markdown.

    Args:
        data: The document's bytes.
        file_name: The uploaded file's name, whose extension picks the converter.
        content_type: The declared media type, used when the name has no
            extension (typically a fetched web page).
        url: Where the document was fetched from, if anywhere.

    Returns:
        The Markdown text and, when the document declares one, its title.

    Raises:
        Exception: Whatever the converter raises for a corrupt or unreadable
            document; the ingest job records it on the source.
    """
    info = _stream_info(file_name, content_type, url)
    return await asyncio.to_thread(_convert, data, info)


def split_chunks(text: str, size: int) -> list[str]:
    """Split text into parts of at most ``size`` characters, at paragraph breaks.

    A cut falls on the last blank line before the limit when there is one in
    the second half of the window, so a part rarely ends mid-paragraph; a
    paragraph longer than half a window is cut where the window ends.

    Args:
        text: The document's Markdown.
        size: Maximum characters per part.

    Returns:
        The non-empty parts, in order.
    """
    parts: list[str] = []
    while len(text) > size:
        cut = text.rfind("\n\n", 0, size)
        if cut < size // 2:
            cut = size
        parts.append(text[:cut].strip())
        text = text[cut:]
    if text.strip():
        parts.append(text.strip())
    return [p for p in parts if p]
