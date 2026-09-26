"""MCPServer data models for create, update, and database persistence.

An MCPServer is a Model Context Protocol server registered with A2Flow.
Registered servers are the catalog the workflow agent draws from when it binds
MCP tools to WorkflowTasks: at design time the agent lists each server's
tools, and at execution time bound tools are invoked through the
``call_mcp_tool`` proxy (see :mod:`infrastructure.mcp_tools`).

Three transports exist, discriminated by ``transport``:

* ``streamable_http`` — a remote server addressed by ``url``. The optional
  ``headers`` mapping (e.g. ``{"Authorization": "Bearer ..."}``) is sent
  verbatim with every request.
* ``stdio`` — a local server launched as a child process of the backend:
  ``command`` (``npx`` or ``uvx``, the only two runtimes the backend image
  ships) plus ``args``, with ``env`` merged over the small set of variables
  :func:`mcp.client.stdio.get_default_environment` deems safe to inherit.
  ``args`` is passed as a list and never through a shell.
* ``script`` — a user-written ``source`` in ``language`` (Python or
  JavaScript), launched like a stdio server through a bundled runner (see
  :mod:`infrastructure.script_runners`) that exposes each public top-level
  function as a tool. ``env`` applies as for stdio; nothing else does.

``headers`` and ``env`` values may embed ``${secret:NAME/KEY}`` placeholders,
resolved at connection time (see :mod:`infrastructure.secret_resolver`), or
``${gcp-token:NAME/KEY}`` placeholders, which mint a Google OAuth 2.0 access
token from the credential JSON that entry holds (see
:mod:`infrastructure.google_token`); anything else is stored in plaintext,
which is acceptable for this app's local, single-operator deployment model.

A stdio server's ``args`` entries may additionally embed ``${env:NAME}``,
referencing a key of that same server's ``env`` map — useful for a launcher
that expects a value as a CLI flag rather than reading it from the process
environment. ``NAME`` must be a key of ``env``, checked eagerly at write time
(:func:`referenced_env_names`, used by this module's ``_validate_shape`` and
by :class:`services.mcp_server.MCPServerService.update`); expansion itself
happens at connection time in :func:`infrastructure.mcp_client.resolve_connection`,
after ``env``'s own ``${secret:NAME/KEY}`` placeholders are resolved — so
``${env:NAME}`` transparently picks up secret-resolved values too.
"""

import ast
import re
import sys
from enum import StrEnum
from typing import Any, Literal

from pydantic import model_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, JSONColumn
from models.constraints import DescText, EntityName, HttpUrl, McpArg, ScriptSource
from models.tenant_scoped import TenantScoped

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Maximum number of header entries allowed on an MCP server.
_MAX_HEADERS = 50

#: Maximum length, in characters, of each header key and value.
_MAX_HEADER_VALUE_LENGTH = 1024

#: Maximum number of environment variables allowed on a stdio MCP server.
_MAX_ENV_VARS = 50

#: Maximum length, in characters, of each environment variable key and value.
_MAX_ENV_VALUE_LENGTH = 4096

#: Maximum number of ``argv`` entries allowed on a stdio MCP server.
_MAX_ARGS = 100

#: Matches ``${env:NAME}`` in an ``args`` entry, referencing a key of this
#: same server's ``env`` mapping. ``NAME`` uses the POSIX env-var charset so
#: the closing ``}`` is unambiguous even though ``env`` keys themselves carry
#: no charset restriction of their own.
ENV_ARG_PLACEHOLDER_PATTERN = re.compile(r"\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}")


def referenced_env_names(args: list[str]) -> set[str]:
    """Return every name referenced via ``${env:NAME}`` across ``args``.

    Args:
        args: The ``argv`` entries to scan.

    Returns:
        The set of referenced names, deduplicated.
    """
    names: set[str] = set()
    for arg in args:
        names.update(ENV_ARG_PLACEHOLDER_PATTERN.findall(arg))
    return names


class McpTransport(StrEnum):
    """How A2Flow reaches an MCP server: over HTTP, as a child process, or as a script."""

    streamable_http = "streamable_http"
    stdio = "stdio"
    script = "script"


class McpCommand(StrEnum):
    """Launcher for a stdio MCP server: the only two runtimes the backend image ships."""

    npx = "npx"
    uvx = "uvx"


class ScriptLanguage(StrEnum):
    """Language of a ``script`` MCP server's ``source``."""

    python = "python"
    javascript = "javascript"


def check_script_syntax(language: ScriptLanguage, source: str) -> None:
    """Reject a Python script that does not compile.

    JavaScript is not checked: the backend image ships no Node.js, so a broken
    JavaScript script surfaces only when its tools are listed.

    Args:
        language: The script's language.
        source: The script's source code.

    Raises:
        ValueError: If ``language`` is Python and ``source`` has a syntax
            error; the message names the offending line.
    """
    if language is not ScriptLanguage.python:
        return
    try:
        compile(source, "<script>", "exec")
    except SyntaxError as exc:
        raise ValueError(
            f"Script syntax error on line {exc.lineno}: {exc.msg}"
        ) from exc


class ScriptDiagnostic(SQLModel):
    """One problem found in a script's source, located for the editor to underline.

    Lines are 1-based; columns are 0-based character offsets within their line.
    Returned by ``POST /mcp-servers/python-lint``.
    """

    model_config = _alias_config
    line: int
    column: int
    end_line: int
    end_column: int
    severity: Literal["error", "warning"]
    message: str


class PythonLintRequest(SQLModel):
    """Body of ``POST /mcp-servers/python-lint``: the Python source to check."""

    source: ScriptSource


def _char_column(lines: list[str], line: int, byte_col: int) -> int:
    """Convert an ``ast`` UTF-8 byte offset on ``line`` (1-based) to characters.

    Args:
        lines: The source split into lines.
        line: The 1-based line the offset is on.
        byte_col: The byte offset ``ast`` reported.

    Returns:
        The same position as a character offset.
    """
    text = lines[line - 1] if 0 < line <= len(lines) else ""
    return len(text.encode()[:byte_col].decode(errors="ignore"))


def _warn_at(lines: list[str], node: ast.AST, message: str) -> ScriptDiagnostic:
    """Build a warning spanning ``node``'s source range.

    Args:
        lines: The source split into lines.
        node: A node carrying position attributes.
        message: The warning text.

    Returns:
        The diagnostic.
    """
    line: int = getattr(node, "lineno", 1)
    end_line: int = getattr(node, "end_lineno", None) or line
    col: int = getattr(node, "col_offset", 0)
    end_col: int = getattr(node, "end_col_offset", None) or col
    return ScriptDiagnostic(
        line=line,
        column=_char_column(lines, line, col),
        end_line=end_line,
        end_column=_char_column(lines, end_line, end_col),
        severity="warning",
        message=message,
    )


def lint_python_script(source: str) -> list[ScriptDiagnostic]:
    """Check a Python script server's source for errors and convention slips.

    A syntax error is reported alone, as an error. A script that compiles is
    checked against the runner's conventions (see
    :mod:`infrastructure.script_runners.python_runner`), each slip a warning:
    no public top-level function (so no tools), a public function's parameter
    without a type hint or the function without a docstring (so a vague tool
    schema), and an import from outside the standard library.

    Args:
        source: The script's source code.

    Returns:
        The diagnostics, in source order per check; empty for a clean script.
    """
    try:
        tree = ast.parse(source, "<script>")
    except SyntaxError as exc:
        line = exc.lineno or 1
        col = max((exc.offset or 1) - 1, 0)
        end_line = exc.end_lineno or line
        end_col = (exc.end_offset or 0) - 1
        if end_line == line and end_col <= col:
            end_col = col + 1
        return [
            ScriptDiagnostic(
                line=line,
                column=col,
                end_line=end_line,
                end_column=end_col,
                severity="error",
                message=exc.msg,
            )
        ]

    lines = source.splitlines()
    diagnostics: list[ScriptDiagnostic] = []
    public = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and not node.name.startswith("_")
    ]
    if not public:
        diagnostics.append(
            ScriptDiagnostic(
                line=1,
                column=0,
                end_line=1,
                end_column=len(lines[0]) if lines else 0,
                severity="warning",
                message="No public top-level function: this server exposes no tools.",
            )
        )
    for fn in public:
        if ast.get_docstring(fn) is None:
            name_col = _char_column(lines, fn.lineno, fn.col_offset)
            # "def" itself may contain the name (``def f``), so match past it.
            header = re.compile(rf"def\s+{re.escape(fn.name)}")
            match = header.search(lines[fn.lineno - 1], name_col)
            name_end = match.end() if match else name_col + 1
            diagnostics.append(
                ScriptDiagnostic(
                    line=fn.lineno,
                    column=name_col,
                    end_line=fn.lineno,
                    end_column=max(name_end, name_col + 1),
                    severity="warning",
                    message=f"'{fn.name}' has no docstring: the tool will have "
                    "no description.",
                )
            )
        params = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
        diagnostics.extend(
            _warn_at(
                lines,
                param,
                f"Parameter '{param.arg}' has no type hint: the tool will accept "
                "any value for it.",
            )
            for param in params
            if param.annotation is None
        )
    for node in ast.walk(tree):
        modules: list[tuple[ast.AST, str]]
        if isinstance(node, ast.Import):
            modules = [(alias, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [(node, node.module)]
        else:
            continue
        diagnostics.extend(
            _warn_at(
                lines,
                where,
                f"'{name}' is not in the standard library, which is all a "
                "script can import.",
            )
            for where, name in modules
            if name.partition(".")[0] not in sys.stdlib_module_names
        )
    return diagnostics


class MCPServerUpdate(SQLModel):
    """Partial update payload for an MCPServer — all fields are optional.

    When ``headers``, ``args``, or ``env`` is ``None`` the stored value is left
    unchanged; when it is a mapping (or list) the stored value is replaced
    wholesale. The per-transport shape rules (which fields must be present or
    absent) are enforced against the merged result by
    :class:`services.mcp_server.MCPServerService`, because a PATCH body alone
    cannot know the effective transport.
    """

    model_config = _alias_config
    name: EntityName | None = None
    description: DescText | None = None
    transport: McpTransport | None = None
    url: HttpUrl | None = None
    headers: dict[str, str] | None = None
    command: McpCommand | None = None
    args: list[McpArg] | None = None
    env: dict[str, str] | None = None
    language: ScriptLanguage | None = None
    source: ScriptSource | None = None

    @model_validator(mode="after")
    def _validate_sizes(self) -> "MCPServerUpdate":
        """Bound the headers/env mappings and the ``args`` list.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If any collection exceeds its entry-count cap, or any
                header/env key or value exceeds its length cap.
        """
        _assert_mapping_within(
            self.headers, _MAX_HEADERS, _MAX_HEADER_VALUE_LENGTH, "Header"
        )
        _assert_mapping_within(
            self.env, _MAX_ENV_VARS, _MAX_ENV_VALUE_LENGTH, "Environment variable"
        )
        if self.args is not None and len(self.args) > _MAX_ARGS:
            raise ValueError(f"At most {_MAX_ARGS} arguments are allowed")
        return self


def _assert_mapping_within(
    mapping: dict[str, str] | None, max_entries: int, max_length: int, label: str
) -> None:
    """Reject a mapping that exceeds its entry-count or key/value length caps.

    Args:
        mapping: The mapping to check; ``None`` passes (the field is unset).
        max_entries: Maximum number of entries allowed.
        max_length: Maximum length, in characters, of each key and each value.
        label: Human-readable field name used in the error messages.

    Raises:
        ValueError: If the mapping has too many entries, or any key or value is
            too long.
    """
    if mapping is None:
        return
    if len(mapping) > max_entries:
        raise ValueError(f"At most {max_entries} {label.lower()} entries are allowed")
    for key, value in mapping.items():
        if len(key) > max_length or len(value) > max_length:
            raise ValueError(
                f"{label} keys and values must be at most {max_length} characters"
            )


class MCPServerCreate(MCPServerUpdate):
    """Creation payload for an MCPServer with required fields.

    ``transport`` defaults to ``streamable_http`` so an existing remote-server
    payload stays valid unchanged.
    """

    name: EntityName
    description: DescText | None = None
    transport: McpTransport = McpTransport.streamable_http
    url: HttpUrl | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    command: McpCommand | None = None
    args: list[McpArg] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    language: ScriptLanguage | None = None
    source: ScriptSource | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "MCPServerCreate":
        """Enforce exactly one shape per transport.

        Returns:
            The validated model instance.

        Raises:
            ValueError: If a ``streamable_http`` server is missing ``url``, a
                ``stdio`` server is missing ``command``, a ``script`` server is
                missing ``language`` or ``source`` (or its Python source does
                not compile), any server carries another transport's fields,
                or a stdio server's ``args`` embed a ``${env:NAME}``
                placeholder naming a key absent from ``env``.
        """
        is_script_shaped = self.language is not None or self.source is not None
        if self.transport is McpTransport.streamable_http:
            if self.url is None:
                raise ValueError("A streamable_http server requires a url")
            if self.command is not None or self.args or self.env or is_script_shaped:
                raise ValueError(
                    "A streamable_http server must not set command, args, env, "
                    "language, or source"
                )
        elif self.transport is McpTransport.stdio:
            if self.command is None:
                raise ValueError("A stdio server requires a command")
            if self.url is not None or self.headers or is_script_shaped:
                raise ValueError(
                    "A stdio server must not set url, headers, language, or source"
                )
            missing = referenced_env_names(self.args) - self.env.keys()
            if missing:
                raise ValueError(
                    "args reference undefined env vars: " + ", ".join(sorted(missing))
                )
        else:
            if self.language is None or self.source is None:
                raise ValueError("A script server requires a language and a source")
            if self.url is not None or self.headers or self.command or self.args:
                raise ValueError(
                    "A script server must not set url, headers, command, or args"
                )
            check_script_syntax(self.language, self.source)
        return self


class MCPServer(MCPServerCreate, TenantScoped, BaseEntity, table=True):
    """Database-persisted MCP server, remote over streamable HTTP or local stdio."""

    __tablename__ = "mcp_servers"
    tenant_id: str = Field(foreign_key="tenants.id", ondelete="RESTRICT")
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_tenant_id_name"),
        Index("ix_mcp_servers_tenant_id_name", "tenant_id", "name"),
    )

    headers: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )
    args: list[str] = Field(
        default_factory=list, sa_column=Column(JSONColumn, nullable=False)
    )
    env: dict[str, str] = Field(
        default_factory=dict, sa_column=Column(JSONColumn, nullable=False)
    )


class McpServerRead(BaseEntity):
    """Read view of an MCPServer returned by the API, including its tags.

    Mirrors every column of :class:`MCPServer` and adds ``tag_ids``, which lives
    in :class:`models.tag.McpServerTag` rather than on the server row. The
    mirroring is not cosmetic: this class is what
    :meth:`repositories.mcp_server.SqlMCPServerRepository.list` passes as
    ``readable=``, and a column missing here becomes unfilterable and
    unsortable through the list API.
    """

    model_config = _alias_config
    tenant_id: str
    name: str
    description: str | None = None
    transport: McpTransport = McpTransport.streamable_http
    url: str | None = None
    headers: dict[str, str] = {}
    command: McpCommand | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    language: ScriptLanguage | None = None
    source: str | None = None
    #: Ids of the tags attached to this server.
    tag_ids: list[str] = []

    @classmethod
    def from_server(cls, server: MCPServer, *, tag_ids: list[str]) -> "McpServerRead":
        """Build the read view of a stored MCP server with its tags attached.

        Args:
            server: The persisted server to project.
            tag_ids: Ids of the tags attached to ``server``.

        Returns:
            A read view carrying the server's columns plus its tags.
        """
        return cls(**server.model_dump(), tag_ids=tag_ids)


class McpToolInfo(SQLModel):
    """A tool advertised by a registered MCP server.

    Returned by ``GET /mcp-servers/{id}/tools`` so the admin UI (and the agent,
    via ``list_mcp_tools``) can present the server's catalog when binding tools
    to WorkflowTasks.
    """

    model_config = _alias_config
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    #: JSON Schema of the tool's structured result, when the server declares one
    #: (MCP spec 2025-06-18 and later). ``None`` means *not declared*, which is
    #: deliberately distinct from the empty schema an unset ``input_schema``
    #: defaults to: the admin UI tells the operator "this tool does not say what
    #: it returns" rather than showing them an empty object.
    output_schema: dict[str, Any] | None = None


class ScriptTestRequest(SQLModel):
    """Body of ``POST /mcp-servers/script-tools``: an unsaved script to load.

    The MCP server form sends what its editor holds, so a script can be tried
    before it is saved. ``env`` values may carry ``${secret:NAME/KEY}``
    placeholders, resolved as for a registered server.
    """

    model_config = _alias_config
    language: ScriptLanguage
    source: ScriptSource
    env: dict[str, str] = Field(default_factory=dict)


class ScriptCallRequest(ScriptTestRequest):
    """Body of ``POST /mcp-servers/script-call``: one tool of an unsaved script to run."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ScriptToolsResult(SQLModel):
    """The tools an unsaved script advertises, or why it could not be loaded.

    A load failure is an answer here, not an HTTP error: ``error`` carries the
    runner's traceback so the author can see what to fix.
    """

    model_config = _alias_config
    tools: list[McpToolInfo] = Field(default_factory=list)
    error: str | None = None


class ScriptCallResult(SQLModel):
    """The outcome of running one tool of an unsaved script.

    ``is_error`` is set both when the tool raised and when the script could not
    be launched at all; ``content`` then carries the message or traceback.
    """

    model_config = _alias_config
    is_error: bool
    content: list[str] = Field(default_factory=list)
    structured: dict[str, Any] | None = None
