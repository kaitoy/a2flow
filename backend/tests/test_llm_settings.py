"""Tests for the resolver that decides which LLM a tenant's agents run on."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_settings
from infrastructure.llm_settings import (
    DEFAULT_LLM_MODEL,
    LlmSettingsResolver,
    ResolvedLlm,
)
from infrastructure.secret_cipher import get_secret_cipher
from models.system_settings import SYSTEM_SETTINGS_ID, SystemSettings
from models.tenant import LlmMode, Tenant
from tests._engine import make_test_engine
from tests._seed import DEFAULT_TEST_TENANT_ID, seed_users


@pytest_asyncio.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Throwaway database holding the default test tenant and system settings."""
    eng = await make_test_engine()
    await seed_users(eng, ids=())
    async with AsyncSession(eng) as session:
        await seed_system_settings(session)
    try:
        yield eng
    finally:
        await eng.dispose()


async def _configure(
    engine: AsyncEngine,
    *,
    system: tuple[str | None, str | None] = (None, None),
    tenant: tuple[LlmMode, str | None, str | None] = (
        LlmMode.system_default,
        None,
        None,
    ),
) -> None:
    """Store the platform's and the default tenant's LLM, encrypting the keys."""
    cipher = get_secret_cipher()

    def encrypted(key: str | None) -> str | None:
        return cipher.encrypt(key) if key else None

    async with AsyncSession(engine) as session:
        settings = await session.get(SystemSettings, SYSTEM_SETTINGS_ID)
        tenant_row = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
        assert settings is not None and tenant_row is not None
        settings.llm_model, settings.llm_api_key = system[0], encrypted(system[1])
        tenant_row.llm_mode = tenant[0]
        tenant_row.llm_model = tenant[1]
        tenant_row.llm_api_key = encrypted(tenant[2])
        session.add(settings)
        session.add(tenant_row)
        await session.commit()


async def _resolve(
    engine: AsyncEngine, tenant_id: str = DEFAULT_TEST_TENANT_ID
) -> ResolvedLlm:
    async with AsyncSession(engine) as session:
        return await LlmSettingsResolver(session, get_secret_cipher()).resolve(
            tenant_id
        )


async def test_nothing_configured_falls_back_to_the_built_in_model(
    engine: AsyncEngine,
) -> None:
    assert await _resolve(engine) == ResolvedLlm(DEFAULT_LLM_MODEL, None)


async def test_the_platform_llm_applies_to_a_tenant_on_system_default(
    engine: AsyncEngine,
) -> None:
    await _configure(engine, system=("litellm:openai/gpt-6.1-sol", "sk-system"))

    assert await _resolve(engine) == ResolvedLlm(
        "litellm:openai/gpt-6.1-sol", "sk-system"
    )


async def test_a_tenants_own_values_are_ignored_on_system_default(
    engine: AsyncEngine,
) -> None:
    await _configure(
        engine,
        system=("gemini-3.8-flash", "sk-system"),
        tenant=(LlmMode.system_default, "litellm:openai/gpt-6.1-sol", "sk-tenant"),
    )

    assert await _resolve(engine) == ResolvedLlm("gemini-3.8-flash", "sk-system")


@pytest.mark.parametrize("mode", [LlmMode.super_admin, LlmMode.tenant_admin])
async def test_a_tenants_own_llm_overrides_the_platforms(
    engine: AsyncEngine, mode: LlmMode
) -> None:
    await _configure(
        engine,
        system=("gemini-3.8-flash", "sk-system"),
        tenant=(mode, "litellm:openai/gpt-6.1-sol", "sk-tenant"),
    )

    assert await _resolve(engine) == ResolvedLlm(
        "litellm:openai/gpt-6.1-sol", "sk-tenant"
    )


async def test_a_super_admin_set_tenant_without_a_key_inherits_the_platforms(
    engine: AsyncEngine,
) -> None:
    await _configure(
        engine,
        system=("gemini-3.8-flash", "sk-system"),
        tenant=(LlmMode.super_admin, "litellm:openai/gpt-6.1-sol", None),
    )

    assert await _resolve(engine) == ResolvedLlm(
        "litellm:openai/gpt-6.1-sol", "sk-system"
    )


async def test_an_admin_set_model_without_the_tenants_key_is_ignored(
    engine: AsyncEngine,
) -> None:
    # Otherwise the tenant's admin could bill any model to the platform's key.
    await _configure(
        engine,
        system=("gemini-3.8-flash", "sk-system"),
        tenant=(LlmMode.tenant_admin, "litellm:openai/gpt-6.1-sol", None),
    )

    assert await _resolve(engine) == ResolvedLlm("gemini-3.8-flash", "sk-system")


async def test_an_admin_set_key_without_a_model_runs_the_platforms_model(
    engine: AsyncEngine,
) -> None:
    await _configure(
        engine,
        system=("gemini-3.8-flash", "sk-system"),
        tenant=(LlmMode.tenant_admin, None, "sk-tenant"),
    )

    assert await _resolve(engine) == ResolvedLlm("gemini-3.8-flash", "sk-tenant")


async def test_a_tenant_without_a_model_inherits_the_platforms(
    engine: AsyncEngine,
) -> None:
    await _configure(
        engine,
        system=("litellm:openai/gpt-6.1-sol", None),
        tenant=(LlmMode.super_admin, None, "sk-tenant"),
    )

    assert await _resolve(engine) == ResolvedLlm(
        "litellm:openai/gpt-6.1-sol", "sk-tenant"
    )


async def test_a_tenant_handed_over_but_not_yet_configured_runs_on_the_platform(
    engine: AsyncEngine,
) -> None:
    await _configure(
        engine,
        system=("gemini-3.8-flash", "sk-system"),
        tenant=(LlmMode.tenant_admin, None, None),
    )

    assert await _resolve(engine) == ResolvedLlm("gemini-3.8-flash", "sk-system")


async def test_an_unknown_tenant_gets_the_platforms_llm(engine: AsyncEngine) -> None:
    await _configure(engine, system=("gemini-3.8-flash", "sk-system"))

    assert await _resolve(engine, "no-such-tenant") == ResolvedLlm(
        "gemini-3.8-flash", "sk-system"
    )


async def test_a_key_that_no_longer_decrypts_is_an_error_not_a_fallback(
    engine: AsyncEngine,
) -> None:
    """Silently using the platform's key would bill the wrong account."""
    await _configure(engine, system=("gemini-3.8-flash", "sk-system"))
    async with AsyncSession(engine) as session:
        tenant = await session.get(Tenant, DEFAULT_TEST_TENANT_ID)
        assert tenant is not None
        tenant.llm_mode = LlmMode.tenant_admin
        tenant.llm_api_key = "not-a-fernet-token"
        session.add(tenant)
        await session.commit()

    with pytest.raises(ValueError):
        await _resolve(engine)
