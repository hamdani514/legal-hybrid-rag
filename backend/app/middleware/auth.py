from typing import Optional, Union
from bson import ObjectId
from fastapi import HTTPException, Request, Depends
from app.api.security import decode_token, TokenError
from app.database import db
from app.models.user import User


async def get_current_user(request: Request) -> User:
    """
    FastAPI dependency to extract and authenticate the current user from the Bearer token.
    Returns the User Beanie document.
    """
    auth_header = request.headers.get("authorization") or ""
    scheme, _, token = auth_header.partition(" ")
    sub = None

    if scheme.lower() == "bearer" and token.strip():
        try:
            payload = decode_token(token.strip())
            sub = payload.get("sub")
        except TokenError:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
    elif request.query_params.get("token"):
        try:
            payload = decode_token(request.query_params.get("token").strip())
            sub = payload.get("sub")
        except TokenError:
            raise HTTPException(status_code=401, detail="Invalid authentication token")

    if not sub:
        # Fallback to x-user-id header if supplied
        sub = request.headers.get("x-user-id") or request.query_params.get("user_id")

    if not sub:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Match by id ("USr-XXXX"), email, or _id (ObjectId)
    sub_str = str(sub).strip()
    user_doc = None

    # Check via Beanie User model
    if ObjectId.is_valid(sub_str):
        user_doc = await User.find_one({"$or": [{"_id": ObjectId(sub_str)}, {"id": sub_str}, {"email": sub_str.lower()}]})
    else:
        user_doc = await User.find_one({"$or": [{"id": sub_str}, {"email": sub_str.lower()}]})

    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")

    return user_doc
