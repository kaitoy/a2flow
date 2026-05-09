from pydantic import BaseModel


class SessionCreate(BaseModel):
    user_id: str
    id: str | None = None


class Session(SessionCreate):
    id: str
    last_update_time: float
