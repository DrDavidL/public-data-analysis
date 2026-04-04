from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import allowlist, user_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _check_allowlist(email: str) -> None:
    if not allowlist.is_allowed(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not in allowlist",
        )


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest) -> TokenResponse:
    _check_allowlist(body.email)
    hashed = hash_password(body.password)
    if not user_store.register(body.email, hashed):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )
    token = create_access_token(body.email)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    _check_allowlist(body.email)
    if not user_store.exists(body.email):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for this email. Please register first.",
        )
    hashed = user_store.get_password_hash(body.email)
    if not hashed or not verify_password(body.password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    token = create_access_token(body.email)
    return TokenResponse(access_token=token)


@router.put("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    email: str = Depends(get_current_user),
) -> MessageResponse:
    hashed = user_store.get_password_hash(email)
    if not hashed or not verify_password(body.current_password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    new_hashed = hash_password(body.new_password)
    user_store.set_password(email, new_hashed)
    return MessageResponse(message="Password changed successfully")


@router.get("/me", response_model=UserResponse)
async def me(email: str = Depends(get_current_user)) -> UserResponse:
    return UserResponse(email=email)
