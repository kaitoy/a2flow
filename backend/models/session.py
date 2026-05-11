from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel


class SessionCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    user_id: str
    id: str | None = None


class Session(SessionCreate):
    id: str
    last_update_time: datetime

    @field_serializer("last_update_time", when_used="json")
    def _serialize_last_update_time(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
