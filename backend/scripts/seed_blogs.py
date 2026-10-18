"""Load backend/seed_data/blogs.json into the `blogs` collection.

Run from the backend directory:

    python -m scripts.seed_blogs

Idempotent by slug: an article already in the database is UPDATED in place
rather than skipped, so editing blogs.json and re-running publishes the edit.
Nothing is ever deleted — an article pulled from the JSON stays in the
database until someone removes it deliberately.
"""

import asyncio
import json
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

# Same compatibility patch as app/database/connection.py and
# scripts/migrate_chat_slugs.py: Beanie calls append_metadata on the client,
# which Motor does not forward to its delegate.
if not hasattr(AsyncIOMotorClient, "append_metadata"):
    AsyncIOMotorClient.append_metadata = lambda self, *a, **kw: getattr(self.delegate, 'append_metadata', lambda *x, **y: None)(*a, **kw)

from beanie import init_beanie

from app.config import settings
from app.models.blog import Blog, parse_published_at

SEED_FILE = Path(__file__).resolve().parents[1] / "seed_data" / "blogs.json"

# Copied onto an existing article on re-seed. `id` and `createdAt` are left
# alone so permalinks and insertion order survive.
CONTENT_FIELDS = (
    "title",
    "excerpt",
    "category",
    "readTime",
    "publishedAt",
    "publishedOn",
    "isFeatured",
    "author",
    "coverImage",
    "tags",
    "contentHtml",
)


async def _migrate_legacy_bodies() -> None:
    """Bring pre-HTML articles up to the current schema.

    Articles seeded before the body moved to HTML hold a `content` array of
    {heading, body} and no `contentHtml`, which the model refuses to load — so
    this runs on the raw collection, BEFORE the first Beanie read, and gives
    them an empty body for the upsert below to fill.
    """
    collection = Blog.get_pymongo_collection()

    adopted = await collection.update_many(
        {"contentHtml": {"$exists": False}},
        {"$set": {"contentHtml": ""}, "$unset": {"content": ""}},
    )
    if adopted.modified_count:
        print(f"[migrate] {adopted.modified_count} article(s) moved from `content` to `contentHtml`")

    # Anything that gained contentHtml earlier but kept the duplicate array.
    dropped = await collection.update_many(
        {"content": {"$exists": True}}, {"$unset": {"content": ""}}
    )
    if dropped.modified_count:
        print(f"[migrate] dropped the leftover `content` array from {dropped.modified_count} article(s)")


async def seed() -> None:
    print(f"Connecting to MongoDB at {settings.MONGO_URL}...")
    client = AsyncIOMotorClient(settings.MONGO_URL)
    # Only Blog is registered: the seeder touches no other collection, and
    # init_beanie builds the slug unique index as a side effect.
    await init_beanie(database=client[settings.DB_NAME], document_models=[Blog])

    await _migrate_legacy_bodies()

    with open(SEED_FILE, "r", encoding="utf-8") as handle:
        items = json.load(handle)

    inserted = updated = 0

    for item in items:
        # Derived here as well as in the model, so a hand-edited JSON entry
        # with an odd date string is caught now rather than at sort time.
        item["publishedOn"] = parse_published_at(item["publishedAt"])
        if item["publishedOn"] is None:
            print(f"[warn] {item['slug']}: unparseable publishedAt {item['publishedAt']!r} - will sort by createdAt")

        existing = await Blog.find_one(Blog.slug == item["slug"])
        if existing:
            fresh = Blog(**item)
            for field in CONTENT_FIELDS:
                setattr(existing, field, getattr(fresh, field))
            await existing.save()
            updated += 1
            print(f"[updated] {existing.slug}")
        else:
            blog = Blog(**item)
            await blog.insert()
            inserted += 1
            print(f"[inserted] {blog.slug}")

    print(f"Done. {inserted} inserted, {updated} updated, {len(items)} in {SEED_FILE.name}.")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
