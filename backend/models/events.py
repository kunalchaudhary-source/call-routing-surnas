from typing import Any, Dict, Optional

from pydantic import BaseModel


class LogEvent(BaseModel):
    call_sid: Optional[str]
    event: str
    payload: Dict[str, Any]
    timestamp: str
