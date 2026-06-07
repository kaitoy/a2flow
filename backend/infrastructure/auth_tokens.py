"""Opaque session-token generation and hashing utilities.

A login session is identified by a high-entropy random token carried in the
``a2flow_session`` cookie. Only the SHA-256 hash of that token is stored in the
database, so a leak of the table does not expose usable session credentials.
The companion CSRF token is a separate random value stored alongside it and
echoed to the client in a readable cookie for the double-submit defense.
"""

import hashlib
import secrets


def generate_token() -> str:
    """Generate a new high-entropy, URL-safe random token.

    Returns:
        A cryptographically random URL-safe string suitable for use as a
        session or CSRF token.
    """
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a raw token with SHA-256 for storage and lookup.

    Args:
        token: The raw token value from the cookie.

    Returns:
        The lowercase hexadecimal SHA-256 digest of the token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
