from fastapi import APIRouter, Depends

from app.core.security import get_admin_user
from app.schemas.auth import AddEmailRequest, AllowlistResponse
from app.services import allowlist

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/allowlist", response_model=AllowlistResponse)
async def list_allowlist(_admin: str = Depends(get_admin_user)) -> AllowlistResponse:
    return AllowlistResponse(emails=allowlist.list_all())


@router.post("/allowlist", response_model=AllowlistResponse)
async def add_to_allowlist(
    body: AddEmailRequest,
    _admin: str = Depends(get_admin_user),
) -> AllowlistResponse:
    for email in body.emails:
        allowlist.add(email)
    return AllowlistResponse(emails=allowlist.list_all())


@router.delete("/allowlist/{email}", response_model=AllowlistResponse)
async def remove_from_allowlist(
    email: str,
    _admin: str = Depends(get_admin_user),
) -> AllowlistResponse:
    allowlist.remove(email)
    return AllowlistResponse(emails=allowlist.list_all())
