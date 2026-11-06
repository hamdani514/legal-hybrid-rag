import asyncio
from typing import Optional

from loguru import logger

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

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


def _where(url: str) -> str:
    """The MongoDB address for log lines, without any username or password."""
    rest = url.split("://", 1)[-1]
    return rest.rsplit("@", 1)[-1].split("/", 1)[0] or "?"


async def connect_db(wait_s: float | None = None) -> None:
    """Connect, waiting for MongoDB to come up.

    After a reboot (or `docker compose up`) the database can take a few seconds
    longer than the app to accept connections. This used to give up on the
    first failed ping and leave no database behind, so startup then crashed
    with an unrelated error ("connection_string parameter or database parameter
    must be set"). Now it retries for MONGO_CONNECT_WAIT_S and, if MongoDB never
    answers, stops with a message that says so.
    """
    if not db.is_configured:
        return
    wait_s = float(getattr(settings, "MONGO_CONNECT_WAIT_S", 60) if wait_s is None else wait_s)
    where = _where(settings.MONGO_URL)
    deadline = asyncio.get_running_loop().time() + wait_s
    attempt, delay = 0, 1.0
    while True:
        attempt += 1
        # Fail a request in 5 s rather than motor's default 30 s when the
        # database is down, here and for every query afterwards.
        client = AsyncIOMotorClient(settings.MONGO_URL, serverSelectionTimeoutMS=5000)
        try:
            await client.admin.command("ping")
            # ping works without signing in; listing collections does not, so a
            # missing or wrong password is reported here, not at the first query.
            await client[settings.DB_NAME].list_collection_names()
            db.client, db.database = client, client[settings.DB_NAME]
            if attempt > 1:
                logger.info(f"MongoDB at {where} answered after {attempt} attempts.")
            return
        except OperationFailure as e:
            client.close()
            # Retrying cannot fix credentials: say so at once.
            raise RuntimeError(
                f"MongoDB at {where} refused access ({e.code}: {'wrong username or password' if e.code == 18 else 'not signed in'}). "
                "Check the username and password in MONGO_URL."
            ) from None
        except Exception as e:  # noqa: BLE001
            client.close()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise RuntimeError(
                    f"MongoDB at {where} did not answer within {wait_s:.0f}s ({type(e).__name__}). "
                    f"Check that the database is running and MONGO_URL is right."
                ) from None
            logger.warning(f"Waiting for MongoDB at {where} (attempt {attempt}, {remaining:.0f}s left): {type(e).__name__}")
            await asyncio.sleep(min(delay, max(remaining, 0)))
            delay = min(delay * 2, 8.0)


async def close_db() -> None:
    if db.client is not None:
        db.client.close()
    db.client = None
    db.database = None
