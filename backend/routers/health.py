"""Health check router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple ``{"status": "ok"}`` response to confirm the service is running."""
    return {"status": "ok"}
