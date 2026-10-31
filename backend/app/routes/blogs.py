"""Public, read-only blog API.

Mounted in main.py WITHOUT a router guard: articles are marketing content and
must render for signed-out visitors and crawlers.

Two response shapes, built here rather than returned as raw Beanie documents so
the wire contract is pinned in one place:

  * _card    — what a listing needs. Deliberately WITHOUT contentHtml: the hub
               renders nine cards and has no use for nine full article bodies.
  * _article — one post, plus the handful of cards the reader page shows under
               "Related articles".
"""

from fastapi import APIRouter, HTTPException, Response

from app.models.blog import DRAFT, Blog
from app.services.google_drive_service import google_drive_service

router = APIRouter(prefix="/api/blogs", tags=["blogs"])

# How many suggestions the reader page shows beneath an article.
RELATED_LIMIT = 3

# Drafts are withheld from every public response — the listing, the article
# itself, and the related reading under it.
#
# Expressed as "not a draft" rather than "is published" on purpose: articles
# written before the status field existed have no `status` key at all, and a
# {"status": "published"} query would silently hide every one of them.
VISIBLE = {"status": {"$ne": DRAFT}}


def _card(blog: Blog) -> dict:
    return {
        "id": str(blog.id),
        "slug": blog.slug,
        "title": blog.title,
        "excerpt": blog.excerpt,
        "category": blog.category,
        "readTime": blog.readTime,
        "publishedAt": blog.publishedAt,
        "isFeatured": blog.isFeatured,
        "author": blog.author.model_dump(),
        "coverImage": blog.coverImage,
        "tags": blog.tags,
    }


def _article(blog: Blog, related: list) -> dict:
    return {**_card(blog), "contentHtml": blog.contentHtml, "related": related}


@router.get("")
async def list_blogs():
    """Every published article, newest publication date first."""
    blogs = await Blog.find(VISIBLE).sort(-Blog.publishedOn).to_list()
    return [_card(blog) for blog in blogs]


@router.get("/cover/{file_id}")
async def get_blog_cover(file_id: str):
    """A cover image uploaded in the editor, from Google Drive (cached locally).

    Every upload gets a new id, so the response never changes and can be
    cached for good."""
    try:
        data, mime_type = await google_drive_service.download_blog_cover(file_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Cover image not found")
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/{slug}")
async def get_blog_by_slug(slug: str):
    """One published article by its public slug, with its related reading."""
    # A draft is a 404 here, not a 403: the public has no business learning
    # that an unpublished article exists at this address.
    blog = await Blog.find_one({"slug": slug, **VISIBLE})
    if not blog:
        raise HTTPException(status_code=404, detail="Blog post not found")

    # Same category first, then anything else, so a short archive still fills
    # the row instead of showing one lonely card.
    others = await Blog.find({"slug": {"$ne": slug}, **VISIBLE}).sort(-Blog.publishedOn).to_list()
    same_category = [other for other in others if other.category == blog.category]
    rest = [other for other in others if other.category != blog.category]
    related = [_card(other) for other in (same_category + rest)[:RELATED_LIMIT]]

    return _article(blog, related)
