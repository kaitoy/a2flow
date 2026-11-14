"""Password hashing utilities backed by bcrypt.

Provides one-way hashing for user passwords and constant-time verification.
Hashing belongs in the infrastructure layer because it adapts an external
cryptographic primitive (bcrypt) rather than encoding business rules.
"""

import os
from functools import lru_cache

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


def verify_password(plain: str, hashed: str | None) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    Args:
        plain: The plaintext password to verify.
        hashed: The previously stored bcrypt hash, or ``None`` for an account
            that has no password (one that signs in through SSO only).

    A password bcrypt refuses to check -- bcrypt 5 raises ``ValueError`` for
    one longer than 72 bytes -- simply does not match. Letting the error
    propagate would turn a login attempt into a 500 for existing accounts only,
    telling an attacker which usernames are real.

    Returns:
        ``True`` if the password matches the hash, ``False`` otherwise --
        always ``False`` when ``hashed`` is ``None``.
    """
    if hashed is None:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Return a throwaway hash at the configured cost, computed once per process."""
    return hash_password("a2flow-dummy-password")


def burn_password_check(plain: str) -> None:
    """Spend one bcrypt verification on a password that cannot log in anyway.

    Login calls this when the account is missing, disabled, deleted, or its
    tenant is unknown, so those rejections cost the same bcrypt round as a
    wrong password for a real account. Without it the response time alone --
    hundreds of milliseconds at cost 12 -- tells an attacker which usernames
    and tenant slugs exist.

    Args:
        plain: The submitted plaintext password; its result is discarded.
    """
    verify_password(plain, _dummy_hash())
