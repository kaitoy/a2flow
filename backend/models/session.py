from pydantic import BaseModel


class SessionCreate(BaseModel):
    user_id: str
    session_id: str | None = None


class Session(SessionCreate):
    session_id: str
    last_update_time: float
