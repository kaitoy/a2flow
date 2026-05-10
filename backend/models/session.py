from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class SessionCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    user_id: str
    id: str | None = None


class Session(SessionCreate):
    id: str
    last_update_time: datetime
