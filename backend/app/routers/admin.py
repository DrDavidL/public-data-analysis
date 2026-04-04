from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_admin_user, hash_password
from app.schemas.auth import (
    AddEmailRequest,
    AllowlistResponse,
    MessageResponse,
    ResetPasswordRequest,
)
from app.services import allowlist, user_store

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


@router.put("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    _admin: str = Depends(get_admin_user),
) -> MessageResponse:
    hashed = hash_password(body.new_password)
    if not user_store.set_password(body.email, hashed):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No account found for {body.email}",
        )
    return MessageResponse(message=f"Password reset for {body.email}")


@router.delete("/allowlist/{email}", response_model=AllowlistResponse)
async def remove_from_allowlist(
    email: str,
    _admin: str = Depends(get_admin_user),
) -> AllowlistResponse:
    allowlist.remove(email)
    return AllowlistResponse(emails=allowlist.list_all())
