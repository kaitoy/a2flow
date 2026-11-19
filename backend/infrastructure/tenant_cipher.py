"""Hands out the cipher of a tenant's data key to callers holding only its id.

Kept apart from :mod:`infrastructure.secret_cipher` because it reads the
``tenants`` table, and :mod:`models.tenant` itself imports that module to
generate each new tenant's data key.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.secret_cipher import SecretCipher, data_key_cipher
from models.tenant import Tenant


class TenantCiphers:
    """Looks up the cipher every ciphertext of a given tenant is encrypted with."""

    def __init__(self, session: AsyncSession) -> None:
        """Store the session the tenant rows are read through.

        Args:
            session: The SQLModel async session to read ``tenants`` with.
        """
        self._db = session

    async def for_tenant(self, tenant_id: str) -> SecretCipher:
        """Return the cipher of the tenant's data key.

        Args:
            tenant_id: The tenant owning the values to encrypt or decrypt.

        Returns:
            The cipher of that tenant's data key.

        Raises:
            ValueError: If no such tenant exists, or its data key was not
                wrapped with the current master key.
        """
        wrapped = (
            await self._db.exec(select(Tenant.data_key).where(Tenant.id == tenant_id))
        ).first()
        if wrapped is None:
            raise ValueError(f"No tenant {tenant_id!r} to hold a data key")
        return data_key_cipher(wrapped)
