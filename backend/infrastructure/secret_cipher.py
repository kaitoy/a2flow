"""Fernet encryption for local secrets and the key-loading strategy behind it.

The symmetric key is resolved once per process with the following precedence:

1. ``SECRET_ENCRYPTION_KEY`` environment variable — must be a valid Fernet key
   (32 url-safe base64-encoded bytes); an invalid value fails fast so a typo
   cannot silently fall through to a generated key that decrypts nothing.
2. A key file — path from ``SECRET_KEY_FILE``, defaulting to ``.secret_key``
   next to the SQLite database file when ``DB_URL`` is file-backed SQLite,
   else ``.secret_key`` in the working directory.
3. Generated — a fresh Fernet key is created, written to the key-file path
   (permissions restricted best-effort), and a WARNING is logged reminding the
   operator to back it up: losing the key makes every stored local secret
   undecryptable.

That key is the *master* key of an envelope scheme. It encrypts platform-owned
values (SMTP password, platform LLM key, the MCP CA key, the OIDC state cookie)
directly, and otherwise only wraps per-tenant data keys: every tenant row
carries ``data_key``, a random Fernet key encrypted with the master
(:func:`new_data_key`), and everything a tenant owns -- its secrets, its stored
credentials, its MCP tool certificates' private keys -- is encrypted with that
tenant's data key (:func:`data_key_cipher`). A ciphertext of one tenant
therefore never decrypts under another tenant's key.

Rotating the master key: the new key becomes ``SECRET_ENCRYPTION_KEY`` (or the
key file) and the old one moves to ``SECRET_ENCRYPTION_KEY_FALLBACKS``. The
process-wide cipher then encrypts with the new key only but still decrypts with
either (:func:`load_fallback_keys`), and the next startup re-encrypts every
master-encrypted value under the new key
(:func:`infrastructure.bootstrap.rotate_master_key`). Tenant data keys
themselves are unchanged -- only their wrapping is -- so nothing a tenant owns
needs re-encrypting.
"""

import contextlib
import logging
import os
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from config import get_settings
from infrastructure.database import DB_URL, is_sqlite_url

logger = logging.getLogger(__name__)

#: Name of the generated/loaded key file when ``SECRET_KEY_FILE`` is unset.
_DEFAULT_KEY_FILENAME = ".secret_key"


def _default_key_file() -> Path:
    """Return the default key-file path: next to the SQLite DB file, else cwd.

    Returns:
        The resolved default path for the Fernet key file.
    """
    if is_sqlite_url(DB_URL):
        _, _, db_path = DB_URL.partition("///")
        if db_path and db_path != ":memory:":
            return Path(db_path).resolve().parent / _DEFAULT_KEY_FILENAME
    return Path.cwd() / _DEFAULT_KEY_FILENAME


def _validate_key(key: bytes, source: str) -> bytes:
    """Return the key unchanged after checking it is a usable Fernet key.

    Args:
        key: The candidate key material.
        source: Human-readable origin used in the failure message.

    Raises:
        ValueError: If the key is not a valid Fernet key.
    """
    try:
        Fernet(key)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid Fernet key from {source}: {exc}") from exc
    return key


def load_or_create_key() -> bytes:
    """Resolve the Fernet key: env var, then key file, then generate-and-save.

    Returns:
        The Fernet key bytes.

    Raises:
        ValueError: If ``SECRET_ENCRYPTION_KEY`` is set but not a valid Fernet
            key, or the key file exists but holds an invalid key.
    """
    settings = get_settings()
    env_key = settings.secret_encryption_key
    if env_key:
        return _validate_key(
            env_key.encode("ascii", errors="replace"),
            "the SECRET_ENCRYPTION_KEY environment variable",
        )

    key_file = settings.secret_key_file or _default_key_file()
    if key_file.exists():
        return _validate_key(key_file.read_bytes().strip(), f"key file {key_file}")

    key = Fernet.generate_key()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_bytes(key)
    # Best-effort permission tightening; may fail on e.g. Windows ACLs.
    with contextlib.suppress(OSError):
        os.chmod(key_file, 0o600)
    logger.warning(
        "Generated a new secret encryption key at %s. Back this file up (or set "
        "SECRET_ENCRYPTION_KEY): losing the key makes every stored local secret "
        "undecryptable.",
        key_file,
    )
    return key


def load_fallback_keys() -> list[bytes]:
    """Return the previous master keys still accepted for decryption.

    Read from ``SECRET_ENCRYPTION_KEY_FALLBACKS``, a comma-separated list;
    blanks are ignored.

    Returns:
        The fallback keys, in the order given; empty when none is set.

    Raises:
        ValueError: If any listed key is not a valid Fernet key.
    """
    raw = get_settings().secret_encryption_key_fallbacks or ""
    return [
        _validate_key(
            part.strip().encode("ascii", errors="replace"),
            f"entry {index} of SECRET_ENCRYPTION_KEY_FALLBACKS",
        )
        for index, part in enumerate(raw.split(","), start=1)
        if part.strip()
    ]


class SecretCipher:
    """Encrypts and decrypts values with a Fernet key, accepting older keys too."""

    def __init__(self, key: bytes, fallbacks: Sequence[bytes] = ()) -> None:
        """Wrap the given Fernet key, plus any keys it replaced.

        Args:
            key: A valid Fernet key, typically from :func:`load_or_create_key`.
                Every new ciphertext is encrypted with it.
            fallbacks: Previous keys, used only to decrypt values that have
                not been re-encrypted under ``key`` yet.
        """
        self._primary = Fernet(key)
        self._fernet = MultiFernet([self._primary, *(Fernet(k) for k in fallbacks)])
        self._has_fallbacks = bool(fallbacks)

    @property
    def has_fallbacks(self) -> bool:
        """Whether previous keys are configured, i.e. a rotation is under way."""
        return self._has_fallbacks

    def encrypt(self, plain: str) -> str:
        """Encrypt a plaintext value.

        Args:
            plain: The plaintext secret value.

        Returns:
            The Fernet ciphertext as an ASCII string.
        """
        return self._fernet.encrypt(plain.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str, *, ttl: int | None = None) -> str:
        """Decrypt a ciphertext produced by :meth:`encrypt`.

        Args:
            token: The Fernet ciphertext.
            ttl: Maximum age of the ciphertext in seconds; ``None`` accepts
                any age.

        Returns:
            The plaintext secret value.

        Raises:
            ValueError: If the ciphertext is malformed, was encrypted with a
                different key, or is older than ``ttl``.
        """
        try:
            return self._fernet.decrypt(token.encode("ascii"), ttl=ttl).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ValueError("Failed to decrypt stored secret value") from exc

    def rotate(self, token: str) -> str | None:
        """Re-encrypt a ciphertext under the primary key, if it is not already.

        Args:
            token: A ciphertext produced under the primary key or a fallback.

        Returns:
            The ciphertext re-encrypted under the primary key, or ``None`` when
            ``token`` already is under it and needs no rewrite.

        Raises:
            ValueError: If no configured key decrypts ``token``.
        """
        try:
            encoded = token.encode("ascii")
            try:
                self._primary.decrypt(encoded)
                return None
            except InvalidToken:
                return self._fernet.rotate(encoded).decode("ascii")
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ValueError("Failed to decrypt stored secret value") from exc


@lru_cache(maxsize=1)
def get_secret_cipher() -> SecretCipher:
    """Return the process-wide master-key SecretCipher singleton.

    It encrypts with the current master key and also decrypts with the
    ``SECRET_ENCRYPTION_KEY_FALLBACKS`` it replaced.

    Lives here (not in :mod:`dependencies.singletons`, which re-exports it) so
    the agent proxy tools in :mod:`infrastructure.mcp_tools` can use it without
    importing the dependencies package, which would create an import cycle
    through :mod:`infrastructure.agent`.
    """
    return SecretCipher(load_or_create_key(), load_fallback_keys())


def new_data_key() -> str:
    """Generate a tenant data key, wrapped with the master key for storage.

    Returns:
        A fresh Fernet key, encrypted by :func:`get_secret_cipher`.
    """
    return get_secret_cipher().encrypt(Fernet.generate_key().decode("ascii"))


@lru_cache(maxsize=1024)
def data_key_cipher(wrapped: str) -> SecretCipher:
    """Return the cipher of a tenant data key wrapped by :func:`new_data_key`.

    Cached by the wrapped value itself, so a replaced data key simply misses
    the cache and nothing ever needs invalidating.

    Args:
        wrapped: The ``tenants.data_key`` value.

    Returns:
        A cipher encrypting and decrypting with the unwrapped data key.

    Raises:
        ValueError: If ``wrapped`` was not produced under the current master
            key.
    """
    return SecretCipher(get_secret_cipher().decrypt(wrapped).encode("ascii"))
