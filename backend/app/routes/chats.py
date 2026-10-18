from datetime import datetime, timezone
from typing import Union
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.models.chat import Chat, Message
from app.utils.slug import make_slug, ALPHABET, generate
from app.middleware.auth import get_current_user
from app.middleware.plan_guard import plan_guard
from app.services.rag import run_rag_pipeline

router = APIRouter(prefix="/api/chats", tags=["chats"])


# ============================================================
# REQUEST MODELS
# ============================================================

class CreateChatBody(BaseModel):
    firstMessage: str


class AppendMessageBody(BaseModel):
    role: str
    content: str
    sources: list = []


def _get_user_id(user) -> Union[ObjectId, str]:
    """Handle both dict and Beanie document returns from auth middleware."""
    if isinstance(user, dict):
        uid = user.get("_id") or user.get("id")
        return ObjectId(str(uid)) if ObjectId.is_valid(str(uid)) else uid
    return getattr(user, "id", None) or getattr(user, "_id", None)


# ============================================================
# POST /api/chats — Create chat + first message
# Plan guard runs FIRST (via dependency injection)
# ============================================================
@router.post("")
async def create_chat(
    body: CreateChatBody,
    user = Depends(plan_guard),
):
    """
    Creates conversation + first message.
    Plan guard already verified quota (runs before this function body).
    """
    user_id = _get_user_id(user)
    first_msg = body.firstMessage.strip()

    if not first_msg:
        raise HTTPException(400, "First message cannot be empty")

    # Race-safe chat creation with rollback
    chat = await _create_chat_safely(user_id, first_msg)

    # Run RAG
    rag_result = await run_rag_pipeline(first_msg, user_id=str(user_id))

    # Save assistant message
    assistant_msg = Message(
        conversationId=chat.id,
        role="assistant",
        content=rag_result["answer"],
        sources=rag_result.get("sources", []),
    )
    await assistant_msg.insert()

    chat.messageCount = 2
    chat.lastMessageAt = datetime.now(timezone.utc)
    await chat.save()

    return {
        "slug": chat.slug,
        "title": chat.title,
        "chatId": str(chat.id),
        "answer": rag_result["answer"],
        "sources": rag_result.get("sources", []),
    }


# ============================================================
# GET /api/chats — List user's chats
# ============================================================
@router.get("")
async def list_chats(
    limit: int = Query(50, le=100),
    user = Depends(get_current_user),
):
    user_id = _get_user_id(user)
    chats = await Chat.find(
        Chat.userId == user_id
    ).sort(-Chat.lastMessageAt).limit(limit).to_list()

    return [
        {
            "slug": c.slug,
            "title": c.title,
            "messageCount": c.messageCount,
            "lastMessageAt": c.lastMessageAt.isoformat(),
        }
        for c in chats
    ]


# ============================================================
# GET /api/chats/{slug} — Fetch full chat (IDOR-guarded)
# ============================================================
@router.get("/{slug}")
async def get_chat(
    slug: str,
    user = Depends(get_current_user),
):
    user_id = _get_user_id(user)

    # IDOR GUARD
    chat = await Chat.find_one(
        Chat.slug == slug,
        Chat.userId == user_id,
    )
    if not chat:
        raise HTTPException(404, "Chat not found or access denied")

    messages = await Message.find(
        Message.conversationId == chat.id
    ).sort(+Message.createdAt).to_list()

    return {
        "slug": chat.slug,
        "title": chat.title,
        "createdAt": chat.createdAt.isoformat(),
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "sources": m.sources,
                "createdAt": m.createdAt.isoformat(),
            }
            for m in messages
        ],
    }


class QueryRequest(BaseModel):
    query: str
    slug: Union[str, None] = None


query_api_router = APIRouter(prefix="/api/query", tags=["query"])


@query_api_router.post("")
@query_api_router.post("/")
async def api_query(
    body: QueryRequest,
    user = Depends(get_current_user),
):
    user_id = _get_user_id(user)
    rag_result = await run_rag_pipeline(body.query, user_id=str(user_id))
    return {
        "answer": rag_result["answer"],
        "sources": rag_result.get("sources", []),
    }


# ============================================================
# POST /api/chats/{slug}/messages — Append
# ============================================================
@router.post("/{slug}/messages")
async def append_message(
    slug: str,
    body: AppendMessageBody,
    user = Depends(get_current_user),
):
    user_id = _get_user_id(user)

    # Only enforce plan quota for user queries, not assistant responses
    if body.role == "user":
        await plan_guard(user)

    # IDOR GUARD
    chat = await Chat.find_one(
        Chat.slug == slug,
        Chat.userId == user_id,
    )
    if not chat:
        raise HTTPException(404, "Chat not found")

    msg = Message(
        conversationId=chat.id,
        role=body.role,
        content=body.content,
        sources=body.sources,
    )
    await msg.insert()

    chat.messageCount += 1
    chat.lastMessageAt = datetime.now(timezone.utc)
    await chat.save()

    return {"messageId": str(msg.id), "messageCount": chat.messageCount}


# ============================================================
# DELETE /api/chats/{slug}
# ============================================================
@router.delete("/{slug}")
async def delete_chat(
    slug: str,
    user = Depends(get_current_user),
):
    user_id = _get_user_id(user)

    # IDOR GUARD
    chat = await Chat.find_one(
        Chat.slug == slug,
        Chat.userId == user_id,
    )
    if not chat:
        raise HTTPException(404, "Chat not found")

    await Message.find(Message.conversationId == chat.id).delete()
    await chat.delete()

    return {"deleted": True, "slug": slug}


# ============================================================
# HELPER — Race-safe chat creation (no orphans)
# ============================================================
async def _create_chat_safely(
    user_id,
    first_message: str,
    max_attempts: int = 5,
) -> Chat:
    """
    Create chat with unique slug.
    Relies on DB unique index to catch races.
    Rolls back chat if message insert fails (prevents orphans).
    """
    title = first_message[:60]

    for attempt in range(max_attempts):
        candidate_slug = make_slug(first_message)
        chat = None

        try:
            # 1. Insert chat
            chat = Chat(
                userId=user_id,
                slug=candidate_slug,
                title=title,
            )
            await chat.insert()

            # 2. Insert first user message
            try:
                user_msg = Message(
                    conversationId=chat.id,
                    role="user",
                    content=first_message,
                )
                await user_msg.insert()
            except Exception as msg_err:
                # Rollback chat if message fails — no orphans
                await chat.delete()
                raise msg_err

            return chat

        except DuplicateKeyError:
            continue

    # Fallback: pure random slug
    fallback = f"chat-{generate(ALPHABET, 12)}"
    chat = Chat(userId=user_id, slug=fallback, title=title)
    await chat.insert()
    return chat
