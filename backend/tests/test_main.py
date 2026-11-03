"""Tests for module-level startup guards and the startup bootstrap in ``main``."""

import asyncio

import pytest

import main
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


async def test_concurrent_startups_bootstrap_one_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replicas starting together must not migrate or seed concurrently.

    Every step is a no-op except the first and last, which bracket the whole
    sequence: if two bootstraps overlap, one starts while another is mid-way.
    """
    running = 0
    overlapped = False

    async def enter() -> None:
        nonlocal running, overlapped
        running += 1
        overlapped = overlapped or running > 1
        await asyncio.sleep(0.05)

    async def leave(_session: object) -> list[str]:
        nonlocal running
        running -= 1
        return []

    async def noop(_session: object) -> None:
        return None

    monkeypatch.setattr(main, "run_migrations", enter)
    for name in (
        "seed_system_user",
        "provision_transport_credentials",
        "seed_system_settings",
        "apply_system_settings_env_overrides",
        "seed_root_user",
        "seed_default_tenant_and_admin_user",
    ):
        monkeypatch.setattr(main, name, noop)
    monkeypatch.setattr(main, "sync_demo_data", leave)

    await asyncio.gather(*(main._bootstrap() for _ in range(3)))
    assert not overlapped
