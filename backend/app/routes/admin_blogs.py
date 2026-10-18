"""Admin blog authoring: create, edit and delete articles.

Mounted under /api/admin/blogs so it inherits admin_router_guard from main.py
— the public reader API in app/routes/blogs.py stays read-only and unguarded,
and every write goes through this module.

`contentHtml` arrives from the rich-text editor (frontend/src/components/
editor). It is stored as given and sanitized at render time by the shared
allowlist in frontend/src/lib/richText.js, which every reading path goes
through. Size is capped here so one article cannot be made large enough to
slow the public listing.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

from app.models.blog import PUBLISHED, STATUSES, AuthorInfo, Blog, parse_published_at
from app.utils.slug import slugify

router = APIRouter(prefix="/api/admin/blogs", tags=["admin-blogs"])

# Roughly 400KB of markup. Articles are prose; anything beyond this is a
# runaway paste or an image embedded as a data: URI.
MAX_CONTENT_CHARS = 400_000


class BlogPayload(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    slug: Optional[str] = Field(default=None, max_length=120)
    excerpt: str = Field(default="", max_length=1000)
    category: str = Field(default="General", max_length=80)
    readTime: str = Field(default="", max_length=40)
    publishedAt: str = Field(default="", max_length=40)
    status: str = PUBLISHED
    isFeatured: bool = False
    author: AuthorInfo
    coverImage: str = Field(default="", max_length=2000)
    tags: List[str] = []
    contentHtml: str = ""

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        # An unrecognised status would be neither draft nor published, and the
        # public filter ("not a draft") would publish it by accident.
        if value not in STATUSES:
            raise ValueError(f"status must be one of {', '.join(STATUSES)}")
        return value


def _admin_row(blog: Blog) -> dict:
    """List shape for the admin table — no body, same as the public listing."""
    return {
        "id": str(blog.id),
        "slug": blog.slug,
        "title": blog.title,
        "category": blog.category,
        "readTime": blog.readTime,
        "publishedAt": blog.publishedAt,
        "status": blog.status,
        "isFeatured": blog.isFeatured,
        "author": blog.author.model_dump(),
        "coverImage": blog.coverImage,
        "tags": blog.tags,
        "updatedAt": blog.createdAt.isoformat(),
    }


def _full(blog: Blog) -> dict:
    return {**_admin_row(blog), "excerpt": blog.excerpt, "contentHtml": blog.contentHtml}


def _validate(payload: BlogPayload) -> None:
    if len(payload.contentHtml) > MAX_CONTENT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Article body is {len(payload.contentHtml):,} characters; the limit is {MAX_CONTENT_CHARS:,}.",
        )


async def _unique_slug(desired: str, *, ignore: Optional[str] = None) -> str:
    """A slug nobody else holds. `ignore` is the article's own current slug."""
    base = slugify(desired) or "article"
    candidate = base
    attempt = 2
    while True:
        clash = await Blog.find_one(Blog.slug == candidate)
        if not clash or clash.slug == ignore:
            return candidate
        candidate = f"{base}-{attempt}"
        attempt += 1


@router.get("")
async def list_blogs_for_admin():
    """Every article, newest first — including ones with an empty body."""
    blogs = await Blog.find_all().sort(-Blog.publishedOn).to_list()
    return [_admin_row(blog) for blog in blogs]


@router.get("/{slug}")
async def get_blog_for_admin(slug: str):
    blog = await Blog.find_one(Blog.slug == slug)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return _full(blog)


@router.post("")
async def create_blog(payload: BlogPayload):
    _validate(payload)

    slug = await _unique_slug(payload.slug or payload.title)
    published_at = payload.publishedAt or datetime.now(timezone.utc).strftime("%b %d, %Y")

    blog = Blog(
        **payload.model_dump(exclude={"slug", "publishedAt"}),
        slug=slug,
        publishedAt=published_at,
        publishedOn=parse_published_at(published_at),
    )

    try:
        await blog.insert()
    except DuplicateKeyError:
        # Another author took the slug between the check and the insert.
        raise HTTPException(status_code=409, detail="That slug is already in use. Try again.")

    return _full(blog)


@router.put("/{slug}")
async def update_blog(slug: str, payload: BlogPayload):
    _validate(payload)

    blog = await Blog.find_one(Blog.slug == slug)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog post not found")

    # Renaming the slug changes the article's public URL, so it only happens
    # when the author actually edits that field.
    desired = payload.slug or blog.slug
    if desired != blog.slug:
        blog.slug = await _unique_slug(desired, ignore=blog.slug)

    blog.title = payload.title
    blog.excerpt = payload.excerpt
    blog.category = payload.category
    blog.readTime = payload.readTime
    blog.status = payload.status
    blog.isFeatured = payload.isFeatured
    blog.author = payload.author
    blog.coverImage = payload.coverImage
    blog.tags = payload.tags
    blog.contentHtml = payload.contentHtml

    if payload.publishedAt:
        blog.publishedAt = payload.publishedAt
        blog.publishedOn = parse_published_at(payload.publishedAt) or blog.publishedOn

    try:
        await blog.save()
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="That slug is already in use.")

    return _full(blog)


@router.delete("/{slug}")
async def delete_blog(slug: str):
    blog = await Blog.find_one(Blog.slug == slug)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog post not found")

    await blog.delete()
    return {"deleted": True, "slug": slug}
