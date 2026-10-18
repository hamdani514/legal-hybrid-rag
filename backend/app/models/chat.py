from datetime import datetime, timezone
from typing import Optional, List, Union
from beanie import Document, Indexed, PydanticObjectId
from pydantic import Field


class Chat(Document):
    """
    Parent conversation metadata.
    Created ONLY when user sends first message on /chat/new.
    """
    userId: Union[PydanticObjectId, str]
    slug: str                                    # NOT Indexed here — unique compound index created at startup
    title: str = "New Chat"
    messageCount: int = 0
    lastMessageAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "conversations"
        indexes = [
            [("userId", 1), ("lastMessageAt", -1)],   # sidebar sorting
        ]


class Message(Document):
    """
    Child message records. One row per user/assistant turn.
    """
    conversationId: Union[PydanticObjectId, str]
    role: str                                    # "user" | "assistant"
    content: str
    sources: List[dict] = []
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "messages"
        indexes = [
            [("conversationId", 1), ("createdAt", 1)],  # chronological fetch
        ]
