"""Helpers shared by the routes that serve a file as a download."""

from urllib.parse import quote


def content_disposition(name: str) -> str:
    """Build a ``Content-Disposition`` header value that downloads ``name`` as a file.

    Always ``attachment``: a downloaded file's bytes are whatever a participant,
    an agent, or an LLM put there, and serving arbitrary uploaded content inline
    is how an upload endpoint turns into a stored-XSS vector. The name is emitted
    twice --
    a quoted ASCII form every client understands, and the RFC 5987 ``filename*``
    form that carries the real, possibly non-ASCII name.

    Args:
        name: The stored file name.

    Returns:
        The header value.
    """
    fallback = name.encode("ascii", "replace").decode("ascii")
    fallback = fallback.replace('"', "'").replace("\\", "_")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
