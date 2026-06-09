"""Endpoints for listing and reading the current user's notifications.

Notifications are always scoped to the authenticated user resolved from the
session cookie (``CurrentUserIdDep``); there is no way to address another user's
notifications through this router.
"""

from fastapi import APIRouter

from dependencies import (
    ApiMetaDep,
    CurrentUserIdDep,
    NotificationServiceDep,
    PaginationDep,
)
from models.notification import Notification
from models.response import ApiResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=ApiResponse[list[Notification]])
async def list_notifications(
    service: NotificationServiceDep,
    user_id: CurrentUserIdDep,
    pagination: PaginationDep,
    meta: ApiMetaDep,
    unread_only: bool = False,
) -> ApiResponse[list[Notification]]:
    """Return the current user's notifications, newest first.

    When ``unread_only`` is ``true`` only unread notifications are returned, which
    the toolbar bell uses to drive its unread badge.
    """
    items = await service.list(
        user_id=user_id,
        limit=pagination.limit,
        offset=pagination.offset,
        unread_only=unread_only,
    )
    return ApiResponse(meta=meta, data=items)


@router.patch("/{notification_id}", response_model=ApiResponse[Notification])
async def mark_notification_read(
    notification_id: str,
    service: NotificationServiceDep,
    user_id: CurrentUserIdDep,
    meta: ApiMetaDep,
) -> ApiResponse[Notification]:
    """Mark one of the current user's notifications as read.

    Raises HTTP 404 if the notification does not exist or belongs to another user.
    """
    notification = await service.mark_read(notification_id, user_id=user_id)
    return ApiResponse(meta=meta, data=notification)
