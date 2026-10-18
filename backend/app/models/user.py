from datetime import datetime
from typing import Optional, Dict, Any
from beanie import Document, PydanticObjectId
from pydantic import Field


class User(Document):
    id: Optional[PydanticObjectId] = Field(default=None, alias="_id")
    userId: Optional[str] = Field(default=None, alias="id")
    email: Optional[str] = None
    plan: Optional[str] = "Free"
    subscriptionEndsAt: Optional[datetime] = None
    dailyQueries: Optional[Dict[str, Any]] = Field(default_factory=dict)

    class Settings:
        name = "users"
        validate_on_save = False
        extra = "allow"
