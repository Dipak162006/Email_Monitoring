from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_password_hash, verify_password
from app.modules.auth.models import User
from app.modules.auth.schemas import UserRegister


class AuthService:
    """Service handling user data access, password hashing, and authentication logic."""

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Fetch an active or inactive user by normalized email."""
        normalized_email = email.lower().strip()
        result = await db.execute(select(User).where(User.email == normalized_email))
        return result.scalars().first()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """Fetch a user by database ID."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    @staticmethod
    async def create_user(db: AsyncSession, user_in: UserRegister) -> User:
        """Create a new user with bcrypt-hashed password."""
        normalized_email = user_in.email.lower().strip()
        hashed_password = get_password_hash(user_in.password)

        db_user = User(
            email=normalized_email,
            hashed_password=hashed_password,
            full_name=user_in.full_name,
            is_active=True,
            is_superuser=False,
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> Optional[User]:
        """Authenticate a user by email and plaintext password."""
        user = await AuthService.get_user_by_email(db, email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        user: User,
        full_name: str,
    ) -> User:
        """Update authenticated user's display name."""
        user.full_name = full_name.strip()
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user: User,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Verify current password and update with newly hashed password.

        Returns False if current password verification fails.
        """
        if not verify_password(current_password, user.hashed_password):
            return False
        user.hashed_password = get_password_hash(new_password)
        await db.commit()
        await db.refresh(user)
        return True
