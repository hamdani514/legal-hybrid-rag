"""
Chat history: every research conversation a user has, stored per user.

Why this exists
---------------
The research screen kept its conversation in React state only, so a refresh,
a logout or a second device lost everything the user had asked and every
judgment the system had returned. This stores conversations the way a chat
assistant does: a list of sessions in the sidebar, each holding the user's
questions and the system's answers in order, reopenable at any time.

Shape
-----
One document per conversation in `chat_sessions`:

    session_id   uuid4
    user_key     who owns it (see _user_key)
    title        taken from the first question, renameable
    pinned       kept at the top of the list, and never auto-pruned
    messages     the UI's own message objects, stored verbatim so reopening a
                 conversation restores exactly what was on screen - including
                 the judgments, their confidence labels and the drafted answer
    created_at / updated_at

Messages are stored as the frontend sends them rather than re-modelled here,
because the result cards are the frontend's shape (ResultsPanel) and any
re-modelling would silently drop a field the panel needs on reload.

Who owns a conversation
-----------------------
The verified token's subject, and nothing the client sends. Every query filters
on user_key, so a user can only ever read or delete their own conversations.

Bounded on purpose
------------------
A judgment result card is a few KB, so an unbounded conversation would grow
into MongoDB's 16 MB document limit and an unbounded session list would grow
without end on a deployed server. Both are capped (MAX_MESSAGES_PER_SESSION,
MAX_SESSIONS_PER_USER): the oldest are dropped first.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from app.api.security import caller_id
from app.database import db

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_SESSIONS_PER_USER = 100
MAX_MESSAGES_PER_SESSION = 400
# A whole conversation must stay far below MongoDB's 16 MB document limit.
MAX_SESSION_BYTES = 4 * 1024 * 1024
MAX_TITLE_CHARS = 120
TITLE_FROM_QUERY_CHARS = 60


def _collection():
    if db.database is None:
        raise HTTPException(status_code=503, detail="Database is not connected.")
    return db.database.chat_sessions


def _user_key(request: Request) -> str:
    """Who the conversation belongs to: the token's subject."""
    return caller_id(request)


def _title_from(text: str) -> str:
    """A short, readable title from the first question."""
    flat = " ".join((text or "").split())
    if not flat:
        return "New research"
    if len(flat) <= TITLE_FROM_QUERY_CHARS:
        return flat
    return flat[:TITLE_FROM_QUERY_CHARS].rsplit(" ", 1)[0] + "…"


def _preview(messages: list) -> str:
    for m in messages:
        if isinstance(m, dict) and m.get("sender") == "user" and m.get("text"):
            return _title_from(str(m["text"]))
    return ""


def _summary(doc: dict) -> dict:
    """The row the sidebar/history list shows (never the whole conversation)."""
    messages = doc.get("messages") or []
    return {
        "session_id": doc.get("session_id"),
        "title": doc.get("title") or _preview(messages) or "New research",
        "pinned": bool(doc.get("pinned")),
        "message_count": len(messages),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "preview": _preview(messages),
    }


def _trim(messages: list) -> list:
    """Keep a conversation inside the per-session caps, dropping the oldest first."""
    kept = messages[-MAX_MESSAGES_PER_SESSION:]
    while len(kept) > 2 and len(json.dumps(kept, default=str).encode("utf-8")) > MAX_SESSION_BYTES:
        kept = kept[2:]  # drop a question/answer pair
    return kept


class SessionCreate(BaseModel):
    title: str | None = None


class MessagesAppend(BaseModel):
    messages: list[dict] = Field(default_factory=list)


class SessionPatch(BaseModel):
    title: str | None = None
    pinned: bool | None = None


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 50):
    """The caller's conversations, most recently used first (no message bodies)."""
    key = _user_key(request)
    limit = max(1, min(int(limit or 50), MAX_SESSIONS_PER_USER))
    cursor = (_collection().find({"user_key": key}, {"_id": 0})
              .sort([("pinned", -1), ("updated_at", -1)]).limit(limit))
    return {"sessions": [_summary(doc) async for doc in cursor]}


@router.post("/sessions")
async def create_session(body: SessionCreate, request: Request):
    """Start a conversation. The title is set from the first question if absent."""
    key = _user_key(request)
    now = datetime.now(timezone.utc)
    doc = {
        "session_id": str(uuid4()),
        "user_key": key,
        "title": (body.title or "").strip()[:MAX_TITLE_CHARS] or "New research",
        "pinned": False,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }
    await _collection().insert_one(dict(doc))

    # Keep the stored history bounded per user: drop the least recently used.
    try:
        unpinned = {"user_key": key, "pinned": {"$ne": True}}
        total = await _collection().count_documents({"user_key": key})
        if total > MAX_SESSIONS_PER_USER:
            # Pinned conversations are kept on purpose, however old they are.
            stale = _collection().find(unpinned, {"session_id": 1}).sort(
                "updated_at", 1).limit(total - MAX_SESSIONS_PER_USER)
            old_ids = [d["session_id"] async for d in stale]
            if old_ids:
                await _collection().delete_many({"user_key": key, "session_id": {"$in": old_ids}})
                logger.info(f"chat history: pruned {len(old_ids)} old sessions for {key}")
    except Exception as e:  # noqa: BLE001 - pruning must never fail a new conversation
        logger.warning(f"chat history pruning failed for {key}: {e}")

    doc.pop("messages", None)
    return _summary({**doc, "messages": []})


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    """One full conversation, ready to put back on screen."""
    key = _user_key(request)
    doc = await _collection().find_one({"session_id": session_id, "user_key": key}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {**_summary(doc), "messages": doc.get("messages") or []}


@router.post("/sessions/{session_id}/messages")
async def append_messages(session_id: str, body: MessagesAppend, request: Request):
    """Add messages to a conversation, exactly as the screen shows them."""
    key = _user_key(request)
    doc = await _collection().find_one({"session_id": session_id, "user_key": key}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if not body.messages:
        return _summary(doc)

    now = datetime.now(timezone.utc)
    messages = _trim((doc.get("messages") or []) + [dict(m) for m in body.messages])
    update = {"messages": messages, "updated_at": now}
    # An untitled conversation takes its name from the first question asked.
    if doc.get("title") in (None, "", "New research"):
        first = _preview(messages)
        if first:
            update["title"] = first[:MAX_TITLE_CHARS]
    await _collection().update_one({"session_id": session_id, "user_key": key}, {"$set": update})
    return _summary({**doc, **update})


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: SessionPatch, request: Request):
    """Rename a conversation and/or pin it to the top of the list."""
    key = _user_key(request)
    update: dict = {}
    if body.title is not None:
        title = body.title.strip()[:MAX_TITLE_CHARS]
        if not title:
            raise HTTPException(status_code=400, detail="A title is required.")
        update["title"] = title
    if body.pinned is not None:
        update["pinned"] = bool(body.pinned)
    if not update:
        raise HTTPException(status_code=400, detail="Nothing to change.")
    # Pinning deliberately does NOT touch updated_at: it must not reorder the
    # conversation list by pretending the conversation was just used.
    result = await _collection().update_one(
        {"session_id": session_id, "user_key": key}, {"$set": update})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"session_id": session_id, **update}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    """Delete one conversation."""
    key = _user_key(request)
    result = await _collection().delete_one({"session_id": session_id, "user_key": key})
    if not result.deleted_count:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": session_id}


@router.delete("/sessions")
async def clear_sessions(request: Request):
    """Delete every conversation the caller owns."""
    key = _user_key(request)
    result = await _collection().delete_many({"user_key": key})
    return {"deleted": result.deleted_count}


# ─────────────────────────────────────────────────────────────────────────────
# Self-check (scratch database, no network):
#   cd backend && DB_NAME=legal_rag_scratch_chat venv/Scripts/python.exe -m app.api.chat
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import sys

    from app.config import settings

    SCRATCH = "legal_rag_scratch_chat"
    assert settings.DB_NAME == SCRATCH, f"refusing to run against {settings.DB_NAME!r}"

    import httpx

    import main  # noqa: E402
    from app.api.security import create_access_token  # noqa: E402
    from app.database import close_db, connect_db  # noqa: E402

    RESULTS: list = []

    def check(name: str, cond: bool, info: str = "") -> None:
        RESULTS.append(bool(cond))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({info})" if info else ""))

    async def run() -> None:
        await connect_db()
        await db.client.drop_database(SCRATCH)
        await db.database.users.insert_many([{"id": "USr-1001", "email": "a@example.com"}, {"id": "USr-2002", "email": "b@example.com"}])
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as c:
            A, B = "USr-1001", "USr-2002"
            HA = {"Authorization": f"Bearer {create_access_token(A, 'user')}"}
            HB = {"Authorization": f"Bearer {create_access_token(B, 'user')}"}

            r = await c.get("/api/chat/sessions", headers=HA)
            check("a new user has no history", r.status_code == 200 and r.json()["sessions"] == [])

            r = await c.post("/api/chat/sessions", json={}, headers=HA)
            sid = r.json()["session_id"]
            check("conversation created", r.status_code == 200 and sid)

            msgs = [
                {"sender": "user", "text": "A widow claims land given as dower in the nikah nama."},
                {"sender": "ai", "text": "", "query": "A widow claims land...",
                 "citations": [{"judgment_id": "3eff8217", "confidence": "medium",
                                "heading": "Civil Appeal No. 23-P of 2017"}]},
            ]
            r = await c.post(f"/api/chat/sessions/{sid}/messages", json={"messages": msgs}, headers=HA)
            check("messages appended and titled from the question",
                  r.status_code == 200 and r.json()["message_count"] == 2
                  and r.json()["title"].startswith("A widow claims land"), r.json().get("title"))

            r = await c.get(f"/api/chat/sessions/{sid}", headers=HA)
            back = r.json()["messages"]
            check("conversation restores verbatim (citations survive)",
                  back == msgs and back[1]["citations"][0]["confidence"] == "medium")

            r = await c.get("/api/chat/sessions", headers=HA)
            check("it appears in the user's history", len(r.json()["sessions"]) == 1)

            # Isolation between users.
            r = await c.get("/api/chat/sessions", headers=HB)
            check("another user sees none of it", r.json()["sessions"] == [])
            r = await c.get(f"/api/chat/sessions/{sid}", headers=HB)
            check("another user cannot open it", r.status_code == 404, str(r.status_code))
            r = await c.delete(f"/api/chat/sessions/{sid}", headers=HB)
            check("another user cannot delete it", r.status_code == 404, str(r.status_code))

            r = await c.patch(f"/api/chat/sessions/{sid}", json={"title": "Dower dispute"}, headers=HA)
            r2 = await c.get("/api/chat/sessions", headers=HA)
            check("rename works", r.status_code == 200 and r2.json()["sessions"][0]["title"] == "Dower dispute")

            # Ordering: the most recently used conversation comes first.
            r = await c.post("/api/chat/sessions", json={"title": "Second"}, headers=HA)
            sid2 = r.json()["session_id"]
            await c.post(f"/api/chat/sessions/{sid2}/messages",
                         json={"messages": [{"sender": "user", "text": "second question"}]}, headers=HA)
            r = await c.get("/api/chat/sessions", headers=HA)
            check("most recent conversation first", r.json()["sessions"][0]["session_id"] == sid2)

            # Pinning: an older conversation is held above a newer one.
            r = await c.patch(f"/api/chat/sessions/{sid}", json={"pinned": True}, headers=HA)
            check("pin accepted", r.status_code == 200 and r.json().get("pinned") is True)
            r = await c.get("/api/chat/sessions", headers=HA)
            rows = r.json()["sessions"]
            check("pinned conversation sorts to the top even though it is older",
                  rows[0]["session_id"] == sid and rows[0]["pinned"] is True
                  and rows[1]["session_id"] == sid2, [x["session_id"][:6] for x in rows])
            r = await c.patch(f"/api/chat/sessions/{sid}", json={"pinned": False}, headers=HA)
            r2 = await c.get("/api/chat/sessions", headers=HA)
            check("unpin restores recency order",
                  r.status_code == 200 and r2.json()["sessions"][0]["session_id"] == sid2)
            r = await c.patch(f"/api/chat/sessions/{sid}", json={"pinned": True}, headers=HB)
            check("another user cannot pin it", r.status_code == 404, str(r.status_code))

            # Caps: a conversation cannot grow without bound.
            many = [{"sender": "user", "text": f"q{i}"} for i in range(MAX_MESSAGES_PER_SESSION + 50)]
            await c.post(f"/api/chat/sessions/{sid2}/messages", json={"messages": many}, headers=HA)
            r = await c.get(f"/api/chat/sessions/{sid2}", headers=HA)
            kept = r.json()["messages"]
            check("long conversation trimmed to the cap, newest kept",
                  len(kept) == MAX_MESSAGES_PER_SESSION and kept[-1]["text"] == f"q{len(many) - 1}",
                  f"{len(kept)} messages")

            r = await c.delete(f"/api/chat/sessions/{sid}", headers=HA)
            check("owner can delete", r.status_code == 200)
            r = await c.delete("/api/chat/sessions", headers=HA)
            r2 = await c.get("/api/chat/sessions", headers=HA)
            check("clear all empties the history", r.status_code == 200 and r2.json()["sessions"] == [])

            r = await c.get("/api/chat/sessions/does-not-exist", headers=HA)
            check("unknown conversation -> 404", r.status_code == 404)

            # ── nobody else's history ──────────────────────────────────
            r = await c.get("/api/chat/sessions", params={"user_id": A})
            check("no token -> 401, history is private", r.status_code == 401, str(r.status_code))
            r = await c.post("/api/chat/sessions", json={"title": "Mine"}, headers=HA)
            r = await c.get("/api/chat/sessions", params={"user_id": B}, headers=HA)
            titles = [s["title"] for s in r.json()["sessions"]]
            check("a spoofed user_id cannot read another user's history", titles == ["Mine"], str(titles))

        await db.client.drop_database(SCRATCH)
        await close_db()

    asyncio.run(run())
    passed = sum(RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    sys.exit(0 if passed == len(RESULTS) else 1)
