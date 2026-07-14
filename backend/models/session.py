"""Session response model representing an ADK conversation session."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel

from models.base import iso_z


class Session(BaseModel):
    """Lightweight view of an ADK session, returned by the sessions list endpoint."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    user_id: str
    last_update_time: datetime
    title: str | None = None

    @field_serializer("last_update_time", when_used="json")
    def _serialize_last_update_time(self, dt: datetime) -> str:
        """Serialize last_update_time as ISO-8601 with a Z suffix, normalizing naive values to UTC."""
        return iso_z(dt)
