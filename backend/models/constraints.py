"""Reusable field-constraint types shared across the data models.

These ``Annotated`` aliases bundle Pydantic v2 ``StringConstraints`` / ``Field``
validators so that every user-supplied field declares its length bounds, numeric
range, and character-set/format rule exactly once. The same alias is used on the
optional ``EntityUpdate`` declaration (``<Type> | None = None``) and the required
``EntityCreate`` declaration (``<Type>``), keeping the two in sync.

SQLModel disables validation on ``table=True`` classes, so these constraints are
enforced at the request boundary on the non-table ``*Update`` / ``*Create``
models (which FastAPI validates and which feed ``app.openapi()``); the table
model merely inherits them.
"""

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

#: Character set for slug-style identifiers: ASCII letters, digits, ``.``,
#: ``_`` and ``-``. No whitespace or other punctuation.
SLUG_PATTERN = r"^[a-zA-Z0-9._-]+$"

#: Schema-level character rule for human-readable entity names. Excludes the C0
#: control characters, ``DEL``/C1 controls, the no-break space (U+00A0) and the
#: soft hyphen (U+00AD); every printable character and the ordinary half-width
#: space (U+0020) are allowed. This is published in ``openapi.yaml`` and feeds
#: the frontend's generated Zod schema, so it is written with ``\xNN`` escapes
#: only: openapi-ts un-escapes ``\uNNNN`` into literal characters (which breaks
#: the emitted ``/regex/`` literal on the U+2028/U+2029 line separators) but
#: preserves ``\xNN`` as text. The complete non-printable rule — including the
#: higher-plane zero-width, format and separator characters that cannot be
#: expressed here — is enforced on the backend by :func:`_reject_nonprintable`.
ENTITY_NAME_PATTERN = r"^[^\x00-\x1f\x7f-\x9f\xa0\xad]+$"

#: Whitespace characters permitted inside an entity name: the half-width space
#: (U+0020) and the full-width/ideographic space (U+3000). Every other Unicode
#: whitespace/separator character is treated as non-printable.
_ALLOWED_NAME_SPACES = frozenset({"\x20", chr(0x3000)})


def _reject_nonprintable(value: str) -> str:
    """Reject control and other non-printable characters in an entity name.

    Any character whose Unicode general category begins with ``C`` (control,
    format, surrogate, private-use, unassigned) or ``Z`` (line, paragraph, or
    space separator) is rejected, except the two allowed spaces in
    :data:`_ALLOWED_NAME_SPACES`. This complements :data:`ENTITY_NAME_PATTERN`,
    which can only cover the ``<= U+00FF`` subset of these characters.

    Args:
        value: The candidate name to validate.

    Returns:
        The unchanged value when it contains no disallowed characters.

    Raises:
        ValueError: If the value contains a control or non-printable character
            other than a half-width or full-width space.
    """
    for ch in value:
        if ch in _ALLOWED_NAME_SPACES:
            continue
        if unicodedata.category(ch)[0] in ("C", "Z"):
            raise ValueError(
                "must not contain control or non-printable characters; only "
                "half-width and full-width spaces are allowed as whitespace"
            )
    return value


#: Login name: slug charset, 3–64 characters.
Username = Annotated[
    str, StringConstraints(min_length=3, max_length=64, pattern=SLUG_PATTERN)
]

#: Human-readable resource identifier (agent skill / workflow / MCP server name):
#: 1–256 characters. Permits any printable character (unicode letters, digits,
#: punctuation, symbols, emoji) plus the half-width (U+0020) and full-width
#: (U+3000) spaces; control characters and other non-printable characters are
#: rejected. :data:`ENTITY_NAME_PATTERN` enforces the schema-expressible subset
#: and :func:`_reject_nonprintable` enforces the full rule on the backend.
EntityName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=ENTITY_NAME_PATTERN),
    AfterValidator(_reject_nonprintable),
]

#: Free-text personal name (may contain unicode letters/spaces): 1–100 characters.
PersonName = Annotated[str, StringConstraints(min_length=1, max_length=100)]

#: Plaintext password. The 72-character ceiling matches bcrypt's effective byte
#: cap, beyond which extra input is silently truncated by the hasher.
Password = Annotated[str, StringConstraints(min_length=12, max_length=72)]

#: HTTP(S) URL: 1–2048 characters, must start with ``http://`` or ``https://``.
HttpUrl = Annotated[
    str, StringConstraints(min_length=1, max_length=2048, pattern=r"^https?://.+")
]

#: Path within a repository: up to 1024 characters, any character except a
#: backslash and the control characters (C0 ``\x00-\x1f``, DEL/C1 ``\x7f-\x9f``).
RepoPath = Annotated[
    str, StringConstraints(max_length=1024, pattern=r"^[^\x00-\x1f\x7f-\x9f\\]*$")
]

#: Short free-text label such as a task or notification title: 1–200 characters.
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=200)]

#: Free-text description: up to 2000 characters.
DescText = Annotated[str, StringConstraints(max_length=2000)]

#: Notification body text: up to 4000 characters.
BodyText = Annotated[str, StringConstraints(max_length=4000)]

#: Workflow system prompt: 1–20000 characters.
PromptText = Annotated[str, StringConstraints(min_length=1, max_length=20000)]

#: MCP tool name: 1–255 characters.
ToolName = Annotated[str, StringConstraints(min_length=1, max_length=255)]

#: Layout/ordering position: an integer in ``[0, 100000]``.
Position = Annotated[int, Field(ge=0, le=100000)]
