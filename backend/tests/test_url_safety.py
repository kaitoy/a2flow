"""Unit tests for the SSRF host-validation check in infrastructure.url_safety."""

import socket

import pytest

from infrastructure import url_safety
from infrastructure.url_safety import UnsafeUrlError, assert_public_http_url
from infrastructure.url_safety import resolve_host as _real_resolve_host


@pytest.mark.parametrize("scheme", ["ftp", "ssh", "git", "file"])
def test_rejects_non_http_schemes(scheme: str) -> None:
    with pytest.raises(UnsafeUrlError, match="must use http or https"):
        assert_public_http_url(f"{scheme}://example.com/repo")


def test_rejects_missing_host() -> None:
    with pytest.raises(UnsafeUrlError, match="no hostname"):
        assert_public_http_url("http:///path")


def test_rejects_literal_loopback_ipv4() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url("http://127.0.0.1/x")


def test_rejects_literal_loopback_ipv6() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url("http://[::1]/x")


def test_rejects_literal_metadata_ip() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.parametrize(
    "host",
    ["10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.1.1"],
)
def test_rejects_literal_private_ranges(host: str) -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url(f"http://{host}/x")


def test_rejects_literal_link_local_ipv6() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url("http://[fe80::1]/x")


def test_rejects_ipv4_mapped_ipv6_loopback() -> None:
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url("http://[::ffff:127.0.0.1]/x")


def test_allows_literal_public_ip() -> None:
    assert_public_http_url("http://93.184.216.34/x")


def test_rejects_hostname_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(url_safety, "resolve_host", lambda host: ["10.1.2.3"])
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url("http://internal.example.com/x")


def test_allows_hostname_resolving_to_public_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(url_safety, "resolve_host", lambda host: ["93.184.216.34"])
    assert_public_http_url("http://public.example.com/x")


def test_rejects_when_any_of_multiple_resolved_addresses_is_unsafe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        url_safety, "resolve_host", lambda host: ["93.184.216.34", "127.0.0.1"]
    )
    with pytest.raises(UnsafeUrlError, match="disallowed address"):
        assert_public_http_url("http://mixed.example.com/x")


def test_fails_closed_when_resolution_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(host: str) -> list[str]:
        raise UnsafeUrlError(f"could not resolve host {host!r}")

    monkeypatch.setattr(url_safety, "resolve_host", _raise)
    with pytest.raises(UnsafeUrlError, match="could not resolve"):
        assert_public_http_url("http://unresolvable.example.com/x")


def test_resolve_host_wraps_gaierror(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_gaierror(*args: object, **kwargs: object) -> None:
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _raise_gaierror)
    with pytest.raises(UnsafeUrlError, match="could not resolve"):
        _real_resolve_host("nonexistent.invalid")


def test_resolve_host_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    def _slow_getaddrinfo(*args: object, **kwargs: object) -> object:
        time.sleep(1.0)
        return []

    monkeypatch.setattr(url_safety, "DNS_RESOLUTION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(socket, "getaddrinfo", _slow_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="timed out"):
        _real_resolve_host("slow.invalid")


def test_resolve_host_rejects_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(UnsafeUrlError, match="did not resolve"):
        _real_resolve_host("empty.invalid")
