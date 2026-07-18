"""Password hashing utilities backed by bcrypt.

Provides one-way hashing for user passwords and constant-time verification.
Hashing belongs in the infrastructure layer because it adapts an external
cryptographic primitive (bcrypt) rather than encoding business rules.
"""

import os

import bcrypt

#: bcrypt's own default cost factor (2^12 iterations), used when
#: BCRYPT_ROUNDS is unset or not a valid integer. bcrypt.gensalt() requires
#: 4 <= rounds <= 31 and raises ValueError outside that range.
_DEFAULT_BCRYPT_ROUNDS = 12


def _bcrypt_rounds() -> int:
    """Read the bcrypt cost factor from ``BCRYPT_ROUNDS``, uncached.

    Deliberately bypasses ``config.get_settings()`` (unlike every other
    setting - see ``config.py``'s module docstring for why): ``hash_password``
    is invoked from test-fixture setup code before many tests set their own
    env vars in the test body, and reading through that ``lru_cache``d
    singleton here would freeze it prematurely for the whole test.
    """
    raw = os.environ.get("BCRYPT_ROUNDS")
    if raw is None:
        return _DEFAULT_BCRYPT_ROUNDS
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_BCRYPT_ROUNDS


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt and return the encoded hash.

    The cost factor comes from the ``BCRYPT_ROUNDS`` env var, defaulting to
    bcrypt's own default of 12 (see :func:`_bcrypt_rounds`).

    Args:
        plain: The plaintext password to hash.

    Returns:
        The bcrypt hash as a UTF-8 string, safe to store in the database.
    """
    rounds = _bcrypt_rounds()
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode(
        "utf-8"
    )


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    Args:
        plain: The plaintext password to verify.
        hashed: The previously stored bcrypt hash.

    Returns:
        ``True`` if the password matches the hash, ``False`` otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
