"""Tests for module-level startup guards in ``main``."""

import pytest

from main import _validate_cors_origins


def test_validate_cors_origins_rejects_wildcard() -> None:
    """A bare wildcard origin is rejected outright."""
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _validate_cors_origins(["*"])


def test_validate_cors_origins_rejects_wildcard_among_others() -> None:
    """A wildcard mixed into a comma-separated list is still caught."""
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        _validate_cors_origins(["http://localhost:3000", "*"])


def test_validate_cors_origins_accepts_explicit_origins() -> None:
    """Explicit origins pass without raising."""
    _validate_cors_origins(["http://localhost:3000", "https://app.example.com"])
