from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# Motor + Beanie compatibility patch: forward append_metadata to delegate
if not hasattr(AsyncIOMotorClient, "append_metadata"):
    AsyncIOMotorClient.append_metadata = lambda self, *a, **kw: getattr(self.delegate, 'append_metadata', lambda *x, **y: None)(*a, **kw)

from app.config import settings


class DatabaseProxy:
    def __init__(self) -> None:
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None

    @property
    def is_configured(self) -> bool:
        # Treat as configured only when MONGO_URL is explicitly supplied (env/.env)
        # and not blank. This preserves the "not configured" state when omitted.
        return "MONGO_URL" in settings.model_fields_set and bool(settings.MONGO_URL.strip())

    @property
    def is_connected(self) -> bool:
        return self.database is not None

    @property
    def documents(self):
        return self.database.documents if self.database is not None else None

    @property
    def nodes(self):
        return self.database.nodes if self.database is not None else None

    @property
    def jobs(self):
        return self.database.jobs if self.database is not None else None


db = DatabaseProxy()


async def connect_db() -> None:
    if not db.is_configured:
        return

    db.client = AsyncIOMotorClient(settings.MONGO_URL)
    db.database = db.client[settings.DB_NAME]
    try:
        await db.client.admin.command("ping")
    except Exception:
        await close_db()


async def close_db() -> None:
    if db.client is not None:
        db.client.close()
    db.client = None
    db.database = None
