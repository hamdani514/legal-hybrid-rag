from datetime import datetime, timezone
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, DESCENDING, IndexModel

# The display format the seed data and the CMS write, e.g. "Oct 15, 2026".
PUBLISHED_AT_FORMAT = "%b %d, %Y"

# Publication state. A draft exists in the database and in the admin console
# but is never served by the public API.
PUBLISHED = "published"
DRAFT = "draft"
STATUSES = (PUBLISHED, DRAFT)


def parse_published_at(value: str) -> Optional[datetime]:
    """"Oct 15, 2026" -> a sortable datetime. None when the string is free-form."""
    try:
        return datetime.strptime(value.strip(), PUBLISHED_AT_FORMAT).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


class AuthorInfo(BaseModel):
    name: str
    role: str
    avatar: str


class Blog(Document):
    """A published article. Read-only to the public API; written by the seeder
    (backend/scripts/seed_blogs.py) or by hand."""

    slug: str
    title: str
    excerpt: str
    category: str
    readTime: str
    # Kept as the author typed it, because it is what the page prints.
    publishedAt: str
    # The sortable form of publishedAt, derived below. Listing by the display
    # string would order "Oct 02" before "Sep 21" — it sorts lexically.
    publishedOn: Optional[datetime] = None
    # "published" is visible on the site; "draft" is written but withheld.
    # Defaulting to published keeps every article that predates this field
    # visible, and the public queries filter on != "draft" rather than
    # == "published" so a document missing the field is never hidden.
    status: str = PUBLISHED
    isFeatured: bool = False
    author: AuthorInfo
    coverImage: str
    tags: List[str] = []
    # The article body as the rich-text editor stores it: a single HTML
    # fragment of h2/h3/p/ul/ol/a/strong. The reader page derives its "On this
    # page" rail from the h2s, and sanitizes before rendering — this string is
    # author input, so nothing downstream may treat it as trusted markup.
    contentHtml: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _derive_published_on(self):
        if self.publishedOn is None:
            self.publishedOn = parse_published_at(self.publishedAt) or self.createdAt
        return self

    class Settings:
        name = "blogs"
        indexes = [
            # One article per slug: the slug is the public URL.
            IndexModel([("slug", ASCENDING)], unique=True, name="slug_unique"),
            IndexModel([("publishedOn", DESCENDING)], name="publishedOn_desc"),
            # The public listing filters on status and orders by date.
            IndexModel([("status", ASCENDING), ("publishedOn", DESCENDING)], name="status_publishedOn"),
        ]
