from fastapi import APIRouter, Body, Depends, HTTPException, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.core.token_revocation import (
    is_refresh_token_revoked,
    revoke_refresh_token,
)
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LogoutRequest,
    MessageResponse,
    Token,
    TokenRefreshRequest,
    UserLogin,
    UserPasswordChange,
    UserProfileUpdate,
    UserRead,
    UserRegister,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new application user",
)
async def register(
    user_in: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """Register a new user with email and secure password."""
    existing_user = await AuthService.get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = await AuthService.create_user(db, user_in)
    return user


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Log in and obtain a JWT access token",
)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Authenticate user credentials and issue a signed JWT access token."""
    user = await AuthService.authenticate_user(
        db,
        email=login_data.email,
        password=login_data.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.email)
    refresh_token = create_refresh_token(subject=user.email)
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in_seconds,
        refresh_token=refresh_token,
    )


@router.post(
    "/refresh",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token using a valid refresh token",
)
async def refresh_token(
    refresh_in: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """Validate a refresh token and issue a fresh access token and refresh token."""
    try:
        payload = decode_refresh_token(refresh_in.refresh_token)
        user_email = payload.get("sub")
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check whether the refresh token has already been revoked or rotated
    if await is_refresh_token_revoked(refresh_in.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await AuthService.get_user_by_email(db, email=user_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    # Invalidate the current refresh token upon successful rotation
    await revoke_refresh_token(refresh_in.refresh_token)

    new_access_token = create_access_token(subject=user.email)
    new_refresh_token = create_refresh_token(subject=user.email)
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return Token(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=expires_in_seconds,
        refresh_token=new_refresh_token,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Log out and invalidate the refresh token",
)
async def logout(
    logout_data: LogoutRequest = LogoutRequest(),
) -> MessageResponse:
    """Invalidate refresh token server-side so it cannot be used again."""
    if logout_data and logout_data.refresh_token:
        await revoke_refresh_token(logout_data.refresh_token)
    return MessageResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Return the profile information of the currently authenticated user."""
    return current_user


@router.patch(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update authenticated user profile",
)
async def update_profile(
    profile_in: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    """Update display name for the currently authenticated user."""
    updated_user = await AuthService.update_profile(
        db=db,
        user=current_user,
        full_name=profile_in.full_name,
    )
    return updated_user


@router.post(
    "/me/password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change authenticated user password",
)
async def change_password(
    password_data: UserPasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Change password for the currently authenticated user after verifying the current password."""
    success = await AuthService.change_password(
        db=db,
        user=current_user,
        current_password=password_data.current_password,
        new_password=password_data.new_password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )
    return MessageResponse(message="Password changed successfully")
