from fastapi import APIRouter, Depends, HTTPException, status

from app.config import settings
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory user store: email -> hashed password
_users: dict[str, str] = {}


def _check_allowlist(email: str) -> None:
    if settings.allowed_emails and email not in settings.allowed_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not in allowlist",
        )


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest) -> TokenResponse:
    _check_allowlist(body.email)
    if body.email in _users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists",
        )
    _users[body.email] = hash_password(body.password)
    token = create_access_token(body.email)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    _check_allowlist(body.email)
    hashed = _users.get(body.email)
    if not hashed or not verify_password(body.password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(body.email)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(email: str = Depends(get_current_user)) -> UserResponse:
    return UserResponse(email=email)
