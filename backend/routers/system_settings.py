"""Endpoints for the platform-wide system settings.

Every route — reads included — is gated behind the ``super_admin`` role, the
same shape as :mod:`routers.tenant`: these settings are platform-wide, so there
is no tenant-admin or self-service carve-out, and the stored SMTP relay is
infrastructure a tenant admin has no business inspecting.

The routes deliberately do **not** depend on ``CurrentTenantIdDep``. A
``super_admin`` is platform-scoped and carries no ``tenant_id``, so that
dependency would raise ``ForbiddenError`` unless the caller happened to have
selected a tenant — locking the only allowed callers out of their own settings.
Nothing here is tenant-scoped, so the dependency is simply not needed.
"""

import logging

from fastapi import APIRouter, Depends

from dependencies import (
    ApiMetaDep,
    CurrentUserDep,
    CurrentUserIdDep,
    EmailSenderDep,
    SystemSettingsServiceDep,
    require_roles,
)
from models.response import ApiResponse
from models.system_settings import SystemSettingsRead, SystemSettingsUpdate
from models.user import Role
from repositories.exceptions import SystemSettingsValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-settings", tags=["system-settings"])

#: Route dependency gating every system-settings route behind ``super_admin``.
_requires_super_admin = [Depends(require_roles(Role.super_admin))]

#: Subject and body of the message sent by the test-send endpoint.
_TEST_SUBJECT = "A2Flow SMTP test"
_TEST_BODY = (
    "This is a test message from A2Flow.\n\n"
    "If you are reading it, the configured SMTP server can deliver "
    "notification email.\n"
)


@router.get(
    "",
    response_model=ApiResponse[SystemSettingsRead],
    dependencies=_requires_super_admin,
)
async def get_system_settings(
    service: SystemSettingsServiceDep,
    meta: ApiMetaDep,
) -> ApiResponse[SystemSettingsRead]:
    """Return the platform-wide system settings.

    The SMTP password is never included; ``smtpPasswordSet`` reports only
    whether one is stored.
    """
    settings = await service.get()
    return ApiResponse(meta=meta, data=service.to_read(settings))


@router.patch(
    "",
    response_model=ApiResponse[SystemSettingsRead],
    dependencies=_requires_super_admin,
)
async def update_system_settings(
    body: SystemSettingsUpdate,
    service: SystemSettingsServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[SystemSettingsRead]:
    """Apply a partial update to the system settings.

    Omitting ``smtpPassword`` — or sending it as an empty string — keeps the
    stored password, so the admin form can render the field blank without
    clearing it on every save. Sending it as an explicit ``null`` clears the
    stored password.
    """
    settings = await service.update(body, user_id=user_id)
    return ApiResponse(meta=meta, data=service.to_read(settings))


@router.post(
    "/smtp/test",
    response_model=ApiResponse[None],
    dependencies=_requires_super_admin,
)
async def send_smtp_test_email(
    service: SystemSettingsServiceDep,
    sender: EmailSenderDep,
    user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[None]:
    """Send a test message using the stored SMTP settings.

    The message always goes to the calling ``super_admin``'s own address rather
    than one supplied in the request body, so the endpoint cannot be used to
    relay mail to an arbitrary recipient.

    Raises:
        SystemSettingsValidationError: If email delivery is disabled or the
            stored configuration is incomplete, so there is nothing to test.
        EmailSendError: If the relay rejected the message or could not be
            reached.
    """
    config = await service.resolve_smtp()
    if config is None:
        raise SystemSettingsValidationError(
            "Email delivery is not enabled or the SMTP settings are incomplete"
        )
    if not user.email:
        raise SystemSettingsValidationError(
            "The signed-in account has no email address to send a test to"
        )
    await sender.send(config, to=user.email, subject=_TEST_SUBJECT, body=_TEST_BODY)
    logger.info("SMTP test message sent to %s", user.email)
    return ApiResponse(meta=meta, data=None)
