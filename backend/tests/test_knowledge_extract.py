"""Tests for source fetching/extraction and OKF rendering of knowledge pages."""

import io
import zipfile
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
import yaml

from infrastructure.knowledge_extract import (
    KnowledgeFetchError,
    extract_markdown,
    fetch_url,
    is_supported_file,
    split_chunks,
)
from infrastructure.okf import (
    OKF_VERSION,
    build_bundle,
    normalize_page_path,
    render_index,
    render_page,
)
from infrastructure.url_safety import UnsafeUrlError


@dataclass
class _Page:
    """A stand-in satisfying :class:`infrastructure.okf.PageLike`."""

    path: str
    title: str
    type: str = "Concept"
    description: str = ""
    body: str = "Body."
    meta: dict[str, Any] = field(default_factory=dict)


# ---------- extraction ----------


async def test_extract_html_keeps_structure_and_title() -> None:
    html = b"<html><head><title>VPN</title></head><body><h1>Setup</h1><p>Use <b>443</b>.</p></body></html>"
    doc = await extract_markdown(html, content_type="text/html; charset=utf-8")
    assert doc.title == "VPN"
    assert "# Setup" in doc.markdown
    assert "**443**" in doc.markdown


async def test_extract_text_file_by_extension() -> None:
    doc = await extract_markdown("日本語のメモ".encode(), file_name="memo.txt")
    assert doc.markdown == "日本語のメモ"


def test_supported_file_types() -> None:
    assert is_supported_file("Manual.PDF")
    assert is_supported_file("spec.docx")
    assert not is_supported_file("deck.pptx")
    assert not is_supported_file("noextension")


def test_split_chunks_cuts_at_paragraph_breaks() -> None:
    text = "a" * 60 + "\n\n" + "b" * 60 + "\n\n" + "c" * 10
    assert split_chunks(text, 100) == ["a" * 60, "b" * 60 + "\n\n" + "c" * 10]


def test_split_chunks_hard_cuts_a_long_paragraph() -> None:
    assert split_chunks("x" * 250, 100) == ["x" * 100, "x" * 100, "x" * 50]


# ---------- fetching ----------


async def test_fetch_follows_redirects_and_rechecks_every_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []
    monkeypatch.setattr(
        "infrastructure.knowledge_extract.assert_public_http_url", checked.append
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, text="hi", headers={"content-type": "text/plain"})

    fetched = await fetch_url(
        "https://example.com/old",
        max_bytes=100,
        timeout=5,
        transport=httpx.MockTransport(handler),
    )
    assert fetched.data == b"hi"
    assert fetched.url == "https://example.com/new"
    assert checked == ["https://example.com/old", "https://example.com/new"]


async def test_fetch_refuses_a_redirect_to_a_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    with pytest.raises(UnsafeUrlError):
        await fetch_url(
            "https://example.com/",
            max_bytes=100,
            timeout=5,
            transport=httpx.MockTransport(handler),
        )


async def test_fetch_refuses_an_oversized_body() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 101)
    )
    with pytest.raises(KnowledgeFetchError, match="larger than"):
        await fetch_url(
            "https://example.com/", max_bytes=100, timeout=5, transport=transport
        )


async def test_fetch_reports_an_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    with pytest.raises(KnowledgeFetchError, match="404"):
        await fetch_url(
            "https://example.com/", max_bytes=100, timeout=5, transport=transport
        )


# ---------- OKF ----------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/topics/vpn-setup.md", "/topics/vpn-setup.md"),
        ("topics/vpn-setup", "/topics/vpn-setup.md"),
        ("/glossary.md", "/glossary.md"),
    ],
)
def test_normalize_page_path_accepts(raw: str, expected: str) -> None:
    assert normalize_page_path(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "/topics/index.md",
        "/log.md",
        "/Topics/VPN.md",
        "/a/b/c/d/too-deep.md",
        "/topics/../secrets.md",
        "/topics/with space.md",
    ],
)
def test_normalize_page_path_rejects(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_page_path(raw)


def test_render_page_puts_okf_frontmatter_first() -> None:
    page = _Page(
        path="/topics/vpn.md",
        title="VPN",
        description="How remote access works.",
        body="Port 443.[^src-1]\n\n[^src-1]: Manual",
        meta={"sources": [{"id": "src-1", "resource": "manual.pdf"}], "tags": ["net"]},
    )
    rendered = render_page(page)
    head, body = rendered.split("---\n", 2)[1:]
    front = yaml.safe_load(head)
    assert list(front)[:3] == ["type", "title", "description"]
    assert front["sources"] == [{"id": "src-1", "resource": "manual.pdf"}]
    assert front["tags"] == ["net"]
    assert body.strip().startswith("Port 443.")


def test_root_index_lists_pages_and_sections() -> None:
    pages = [
        _Page(path="/overview.md", title="Overview", description="Start here."),
        _Page(path="/procedures/vpn-setup.md", title="VPN setup"),
        _Page(path="/procedures/remote/ssh.md", title="SSH"),
    ]
    root = render_index(pages, "/", title="IT", description="IT knowledge.")
    head, rest = root.split("---\n", 2)[1:]
    assert yaml.safe_load(head) == {"okf_version": OKF_VERSION}
    assert rest.startswith("# IT")
    assert "* [Overview](/overview.md) - Start here." in root
    assert "* [Procedures](/procedures/index.md) - 2 pages" in root
    assert "ssh" not in root

    sub = render_index(pages, "/procedures/", title="IT")
    assert sub.startswith("# Procedures")
    assert "okf_version" not in sub
    assert "* [VPN setup](/procedures/vpn-setup.md)" in sub
    assert "* [Remote](/procedures/remote/index.md) - 1 page" in sub


def test_bundle_has_an_index_per_directory() -> None:
    pages = [
        _Page(path="/overview.md", title="Overview"),
        _Page(path="/procedures/vpn-setup.md", title="VPN setup"),
    ]
    archive = zipfile.ZipFile(io.BytesIO(build_bundle(pages, title="IT")))
    assert sorted(archive.namelist()) == [
        "index.md",
        "overview.md",
        "procedures/index.md",
        "procedures/vpn-setup.md",
    ]
    assert archive.read("overview.md").decode().startswith("---\ntype: Concept\n")
