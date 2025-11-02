from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from schemas.auth import UserRegisterSchema
from security.passwords import hash_password, verify_password


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def create(self, user_data: UserRegisterSchema) -> User:
        hashed_password = hash_password(user_data.password)

        new_user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password,
            is_active=True,
        )

        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)

        return new_user

    async def authenticate(self, username: str, password: str) -> Optional[User]:
        user = await self.get_by_username(username)

        if user is None:
            return None

        if not verify_password(password, user.hashed_password):
            return None

        return user

    async def exists_by_username(self, username: str) -> bool:
        user = await self.get_by_username(username)
        return user is not None

    async def exists_by_email(self, email: str) -> bool:
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()
        return user is not None