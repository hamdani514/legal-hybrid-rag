"""Admin blog authoring: create, edit and delete articles.

Mounted under /api/admin/blogs so it inherits admin_router_guard from main.py
— the public reader API in app/routes/blogs.py stays read-only and unguarded,
and every write goes through this module.

`contentHtml` arrives from the rich-text editor (frontend/src/components/
editor). It is stored as given and sanitized at render time by the shared
allowlist in frontend/src/lib/richText.js, which every reading path goes
through. Size is capped here so one article cannot be made large enough to
slow the public listing.

Cover images uploaded in the editor go to the "Verdict AI Blog Covers" folder
on Google Drive and are referenced by URL, /api/blogs/cover/<file id>. When an
article is saved with a different cover, or deleted, its old uploaded cover is
deleted from Drive. Pasted external URLs are left alone.
"""

import re
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

from app.models.blog import PUBLISHED, STATUSES, AuthorInfo, Blog, parse_published_at
from app.services.google_drive_service import google_drive_service
from app.utils.slug import slugify

router = APIRouter(prefix="/api/admin/blogs", tags=["admin-blogs"])

# Roughly 400KB of markup. Articles are prose; anything beyond this is a
# runaway paste or an image embedded as a data: URI.
MAX_CONTENT_CHARS = 400_000

COVER_URL_PREFIX = "/api/blogs/cover/"
COVER_MAX_BYTES = 5 * 1024 * 1024
COVER_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


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


def _cover_id(url: str) -> Optional[str]:
    """The Drive id in an uploaded cover's URL; None for a pasted external URL."""
    url = (url or "").split("?", 1)[0]
    if not url.startswith(COVER_URL_PREFIX):
        return None
    return url[len(COVER_URL_PREFIX):] or None


async def _drop_cover(url: str) -> None:
    """Delete an uploaded cover from Drive unless an article still shows it."""
    file_id = _cover_id(url)
    if not file_id:
        return
    still_used = rf"^{re.escape(COVER_URL_PREFIX + file_id)}(\?|$)"
    if await Blog.find_one({"coverImage": {"$regex": still_used}}):
        return
    try:
        await google_drive_service.delete_blog_cover(file_id)
    except Exception as e:
        # A leftover file in Drive is not worth failing the save over.
        logger.warning(f"Could not delete old blog cover {file_id}: {e}")


@router.post("/cover")
async def upload_cover(file: UploadFile = File(...)):
    """Store a cover image on Drive and return the URL the article will use.

    The article itself is not touched until it is saved, so a cover chosen
    and then abandoned never replaces the published one."""
    mime_type = (file.content_type or "").lower()
    if mime_type not in COVER_TYPES:
        raise HTTPException(status_code=400, detail="Cover must be a PNG, JPG, WEBP or GIF image.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The image file is empty.")
    if len(content) > COVER_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Cover image must be under 5 MB.")

    filename = file.filename or f"cover{COVER_TYPES[mime_type]}"
    res = await google_drive_service.upload_blog_cover(content, filename, mime_type)
    return {"url": f"{COVER_URL_PREFIX}{res['file_id']}", "fileId": res["file_id"], "status": res["status"]}


@router.delete("/cover/{file_id}")
async def discard_cover(file_id: str):
    """Delete an upload that was replaced before the article was saved.
    A cover a saved article still uses is kept."""
    await _drop_cover(f"{COVER_URL_PREFIX}{file_id}")
    return {"deleted": True, "fileId": file_id}


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
    previous_cover = blog.coverImage
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

    # Only after the save: the new cover is live, so the old one can go.
    if previous_cover != blog.coverImage:
        await _drop_cover(previous_cover)

    return _full(blog)


@router.delete("/{slug}")
async def delete_blog(slug: str):
    blog = await Blog.find_one(Blog.slug == slug)
    if not blog:
        raise HTTPException(status_code=404, detail="Blog post not found")

    await blog.delete()
    await _drop_cover(blog.coverImage)
    return {"deleted": True, "slug": slug}
