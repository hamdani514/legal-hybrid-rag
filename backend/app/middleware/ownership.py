from typing import Type, TypeVar, Union
from fastapi import HTTPException
from beanie import Document, PydanticObjectId
from bson import ObjectId

T = TypeVar('T', bound=Document)


async def get_owned_or_404(
    model: Type[T],
    resource_id: Union[PydanticObjectId, ObjectId, str],
    user_id: Union[PydanticObjectId, ObjectId, str],
    user_field: str = "userId",
) -> T:
    """
    Fetch a document only if it belongs to the given user.
    Returns 404 (not 403) to prevent existence leakage.
    """
    clauses = [getattr(model, user_field) == user_id]
    if isinstance(resource_id, (ObjectId, PydanticObjectId)) or ObjectId.is_valid(str(resource_id)):
        resource = await model.find_one(
            model.id == ObjectId(str(resource_id)),
            *clauses,
        )
    else:
        resource = await model.find_one(
            model.id == resource_id,
            *clauses,
        )

    if not resource:
        raise HTTPException(status_code=404, detail="Not found")
    return resource
