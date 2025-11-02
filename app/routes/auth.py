from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import User
from repositories.user_repository import UserRepository
from schemas.auth import (
    UserRegisterSchema,
    UserLoginSchema,
    TokenSchema,
    UserResponseSchema,
)
from security.permissions import get_current_user
from security.token_manager import get_jwt_manager, JWTAuthManager
from exceptions.security import BaseSecurityError


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Creates a new user account",
)
async def register(
    user_data: UserRegisterSchema,
    db: AsyncSession = Depends(get_db),
) -> UserResponseSchema:
    user_repo = UserRepository(db)

    if await user_repo.exists_by_username(user_data.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    if await user_repo.exists_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    new_user = await user_repo.create(user_data)

    return UserResponseSchema.model_validate(new_user)

@router.post(
    "/login",
    summary="Login user",
    description="Authenticates user and returns tokens",
)
async def login(
    credentials: UserLoginSchema,
    db: AsyncSession = Depends(get_db),
    jwt_manager: JWTAuthManager = Depends(get_jwt_manager),
) -> TokenSchema:
    user_repo = UserRepository(db)

    user = await user_repo.authenticate(
        username=credentials.username,
        password=credentials.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    token_data = {"sub": user.username}
    access_token = jwt_manager.create_access_token(data=token_data)
    refresh_token = jwt_manager.create_refresh_token(data=token_data)

    return TokenSchema(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )

@router.post(
    "/refresh",
    summary="Refresh access token",
    description="Get refresh token for new access",
)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
    jwt_manager: JWTAuthManager = Depends(get_jwt_manager),
) -> TokenSchema:
    try:
        payload = jwt_manager.decode_refresh_token(refresh_token)
        username: str = payload.get("sub")

        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

    except BaseSecurityError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(username)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    token_data = {"sub": user.username}
    new_access_token = jwt_manager.create_access_token(data=token_data)
    new_refresh_token = jwt_manager.create_refresh_token(data=token_data)

    return TokenSchema(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )

@router.get(
    "/me",
    summary="Get current user",
    description="Info about user",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponseSchema:
    return UserResponseSchema.model_validate(current_user)
