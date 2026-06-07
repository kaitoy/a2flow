"""Password hashing utilities backed by bcrypt.

Provides one-way hashing for user passwords and constant-time verification.
Hashing belongs in the infrastructure layer because it adapts an external
cryptographic primitive (bcrypt) rather than encoding business rules.
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt and return the encoded hash.

    Args:
        plain: The plaintext password to hash.

    Returns:
        The bcrypt hash as a UTF-8 string, safe to store in the database.
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    Args:
        plain: The plaintext password to verify.
        hashed: The previously stored bcrypt hash.

    Returns:
        ``True`` if the password matches the hash, ``False`` otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
