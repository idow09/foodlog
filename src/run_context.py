from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserMessageCtx:
    user_id: int
    timestamp: datetime
    image_path: str | None = None
