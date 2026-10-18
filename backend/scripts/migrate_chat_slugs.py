import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
if not hasattr(AsyncIOMotorClient, "append_metadata"):
    AsyncIOMotorClient.append_metadata = lambda self, *a, **kw: getattr(self.delegate, 'append_metadata', lambda *x, **y: None)(*a, **kw)
from beanie import init_beanie
from app.config import settings
from app.models.user import User
from app.models.chat import Chat, Message
from app.utils.slug import make_slug


async def migrate():
    print(f"Connecting to MongoDB at {settings.MONGO_URL}...")
    client = AsyncIOMotorClient(settings.MONGO_URL)
    await init_beanie(
        database=client[settings.DB_NAME],
        document_models=[User, Chat, Message],
    )

    chats = await Chat.find(
        {"$or": [
            {"slug": {"$exists": False}},
            {"slug": None},
            {"slug": ""},
        ]}
    ).to_list()

    print(f"Found {len(chats)} chats to migrate")

    for chat in chats:
        chat.slug = make_slug(chat.title or "chat")
        await chat.save()
        print(f"✅ {chat.id} → {chat.slug}")

    print("Migration complete")


if __name__ == "__main__":
    asyncio.run(migrate())
