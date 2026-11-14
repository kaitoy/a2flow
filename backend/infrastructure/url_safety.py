"""Shared SSRF-blocking check for user-supplied HTTP(S) URLs.

Resolves a URL's hostname and rejects it if the URL doesn't use http(s), the
host is missing/unresolvable, or ANY resolved address is loopback, private,
link-local (this range covers the 169.254.169.254 cloud-metadata address),
reserved, multicast, or unspecified. Used both as a Pydantic ``AfterValidator``
composed into ``models.constraints.HttpUrl`` (catches API-level create/update)
and as a pre-connection recheck immediately before the two outbound operations
this app performs against user-supplied URLs (``infrastructure.mcp_client``,
``infrastructure.skill_manager``) — the second call is defense-in-depth against
DNS-rebinding-after-validation and against rows that bypass Pydantic entirely
(``table=True`` SQLModel classes skip field validation; see the precedent
already documented in ``models.agent_skill``/``models.constraints.RepoPath``).

Neither check pins the address the client then connects to: the HTTP and git
clients resolve the hostname again themselves, and a rebinding DNS server can
answer that second lookup with an internal address. :func:`assert_public_address`
closes that gap by checking the peer of each socket a client actually opens,
before anything is sent over it -- wired in through :func:`guard_peer_address`
for the httpx/httpx2 clients and through ``infrastructure.skill_manager``'s
connection classes for dulwich's urllib3.
"""

import ipaddress
import socket
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any
from urllib.parse import urlsplit

import httpx
import httpx2

#: Upper bound, in seconds, for one DNS resolution performed during URL
#: validation. ``socket.getaddrinfo`` has no native timeout parameter, so the
#: call is dispatched to a worker thread and abandoned, from the caller's
#: point of view, if it runs longer than this — otherwise a hung/malicious
#: resolver could block the asyncio event loop indefinitely when this check
#: runs inside a Pydantic validator during request handling.
DNS_RESOLUTION_TIMEOUT_SECONDS = 3.0

#: Schemes this app is willing to fetch or clone over. Rejecting everything
#: else here also closes dulwich's scheme-dispatch fallback to SSH/local-file
#: clients for any ``repo_url`` that reaches this check with a non-http(s)
#: scheme (e.g. a row written directly to the database, bypassing Pydantic).
_ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Bounded worker pool for DNS resolution. Not used as a context manager (a
#: ``with ThreadPoolExecutor()`` block waits for outstanding work on exit,
#: which would defeat the point of the timeout below), so it lives for the
#: process lifetime; a resolution that never returns leaks one worker thread.
_resolver_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="url-safety-dns")


class UnsafeUrlError(ValueError):
    """Raised when a URL is rejected by :func:`assert_public_http_url`.

    Subclasses ``ValueError`` so it can be raised directly from a Pydantic
    ``AfterValidator`` (Pydantic v2 turns a ``ValueError`` raised in a
    validator into a normal field validation error) while still being a
    distinct, catchable type for infrastructure-layer call sites that need to
    translate it into their own domain exception.
    """


def resolve_host(host: str) -> list[str]:
    """Resolve ``host`` to its numeric addresses, bounded by a short timeout.

    This is the seam tests monkeypatch (``infrastructure.url_safety.resolve_host``)
    to avoid depending on real network access.

    Args:
        host: A hostname (not an IP literal — callers should skip this for
            literals, see :func:`assert_public_http_url`).

    Returns:
        Every resolved IPv4/IPv6 address, as strings, deduplicated.

    Raises:
        UnsafeUrlError: If resolution fails or does not complete within
            :data:`DNS_RESOLUTION_TIMEOUT_SECONDS`.
    """
    future = _resolver_pool.submit(
        socket.getaddrinfo, host, None, 0, 0, socket.IPPROTO_TCP
    )
    try:
        infos = future.result(timeout=DNS_RESOLUTION_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        raise UnsafeUrlError(f"resolving host {host!r} timed out") from exc
    except OSError as exc:  # socket.gaierror is an OSError subclass
        raise UnsafeUrlError(f"could not resolve host {host!r}: {exc}") from exc
    addresses = {str(info[4][0]) for info in infos}
    if not addresses:
        raise UnsafeUrlError(f"host {host!r} did not resolve to any address")
    return list(addresses)


def _is_unsafe_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return whether ``addr`` (or its IPv4-mapped form) is disallowed.

    An allowlist rather than a blocklist: anything the stdlib ``ipaddress``
    module does not report as globally routable (``is_global``) is refused --
    loopback, private, link-local (covers the 169.254.169.254 cloud metadata
    address), shared address space (100.64.0.0/10, e.g. Alibaba Cloud's
    100.100.100.200 metadata endpoint), documentation, reserved, and
    unspecified -- plus multicast, which ``is_global`` lets through. The
    address's ``ipv4_mapped`` form is checked too for IPv6, so classification
    does not depend on which Python 3.11+ patch version fixed
    IPv4-mapped-address handling in the stdlib ``ipaddress`` module.

    Args:
        addr: The address to classify.

    Returns:
        ``True`` if the address (or its IPv4-mapped form) falls into any
        disallowed range.
    """
    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [addr]
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        candidates.append(addr.ipv4_mapped)
    return any(not a.is_global or a.is_multicast for a in candidates)


def assert_public_http_url(url: str, *, allowed_hosts: Collection[str] = ()) -> None:
    """Reject ``url`` unless it is http(s) and every resolved address is public.

    Args:
        url: The candidate URL.
        allowed_hosts: Lower-case hostnames exempt from the address checks (an
            operator's explicit allowlist); the scheme and host checks still
            apply.

    Raises:
        UnsafeUrlError: If the scheme isn't http/https, the host is missing,
            resolution fails or times out, or any resolved address is
            not globally routable, or multicast.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"URL {url!r} must use http or https")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError(f"URL {url!r} has no hostname")
    if host.lower() in allowed_hosts:
        return

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    addresses = [str(literal)] if literal is not None else resolve_host(host)
    for addr_str in addresses:
        assert_public_address(addr_str, host=host)


def assert_public_address(addr_str: str, *, host: str | None = None) -> None:
    """Reject ``addr_str`` unless it is globally routable and not multicast.

    Args:
        addr_str: A numeric IPv4/IPv6 address, e.g. a connected socket's peer.
            An IPv6 zone suffix (``fe80::1%eth0``) is accepted.
        host: The hostname the address belongs to, named in the error message.

    Raises:
        UnsafeUrlError: If the address is not globally routable, or multicast.
    """
    if _is_unsafe_address(ipaddress.ip_address(addr_str)):
        raise UnsafeUrlError(
            f"host {host or addr_str!r} resolves to disallowed address {addr_str!r} "
            "(not globally routable, or multicast)"
        )


async def guard_peer_address(request: httpx.Request | httpx2.Request) -> None:
    """``httpx``/``httpx2`` request hook: refuse a connection to a non-public peer.

    Register it as ``event_hooks={"request": [guard_peer_address]}``. It sets
    the request's ``trace`` extension, which the transport calls right after
    opening a new TCP connection and before TLS or any request bytes, and
    checks the connected socket's peer address with
    :func:`assert_public_address`. That is the address the client resolved for
    itself, so a DNS answer that changed since :func:`assert_public_http_url`
    looked is caught. A connection to a proxy (whose host differs from the
    request's) is not checked: the proxy resolves the target, not this process.
    Reused pooled connections were checked when they were opened.

    Args:
        request: The request about to be sent.
    """
    target = request.url.raw_host.decode("ascii")
    connecting_to_target = False

    async def trace(name: str, info: dict[str, Any]) -> None:
        nonlocal connecting_to_target
        if name == "connection.connect_tcp.started":
            connecting_to_target = info["host"] == target
        elif name == "connection.connect_tcp.complete" and connecting_to_target:
            stream = info["return_value"]
            peer = stream.get_extra_info("server_addr")[0]
            try:
                assert_public_address(peer, host=target)
            except UnsafeUrlError:
                await stream.aclose()
                raise

    request.extensions["trace"] = trace
