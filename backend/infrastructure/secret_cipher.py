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
"""

import contextlib
import logging
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

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


class SecretCipher:
    """Encrypts and decrypts local secret values with a Fernet key."""

    def __init__(self, key: bytes) -> None:
        """Wrap the given Fernet key.

        Args:
            key: A valid Fernet key, typically from :func:`load_or_create_key`.
        """
        self._fernet = Fernet(key)

    def encrypt(self, plain: str) -> str:
        """Encrypt a plaintext value.

        Args:
            plain: The plaintext secret value.

        Returns:
            The Fernet ciphertext as an ASCII string.
        """
        return self._fernet.encrypt(plain.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt a ciphertext produced by :meth:`encrypt`.

        Args:
            token: The Fernet ciphertext.

        Returns:
            The plaintext secret value.

        Raises:
            ValueError: If the ciphertext is malformed or was encrypted with a
                different key.
        """
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError) as exc:
            raise ValueError("Failed to decrypt stored secret value") from exc


@lru_cache(maxsize=1)
def get_secret_cipher() -> SecretCipher:
    """Return the process-wide SecretCipher singleton.

    Lives here (not in :mod:`dependencies.singletons`, which re-exports it) so
    the agent proxy tools in :mod:`infrastructure.mcp_tools` can use it without
    importing the dependencies package, which would create an import cycle
    through :mod:`infrastructure.agent`.
    """
    return SecretCipher(load_or_create_key())
