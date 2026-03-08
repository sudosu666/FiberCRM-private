from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..config import settings
from ..auth import get_password_hash
from ..rate_limit import enforce_http_rate_limit
from ..models import User
from ..schemas import LoginRequest, Token, UserCreate, UserRead, UserRole, UserRoleUpdate
from .auth_helpers import (
    authenticate_user,
    create_token_response,
    get_current_user,
    get_user_by_phone,
    require_roles,
    user_role_values,
)
from ..database import get_session

router = APIRouter(prefix='')
dispatcher_only = Depends(require_roles(UserRole.Dispatcher))

@router.post('/token', response_model=Token)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    enforce_http_rate_limit(
        request,
        scope="auth.login",
        limit=settings.rate_limit_auth_per_minute,
        key_suffix=form_data.username,
    )
    user = await authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Incorrect credentials')
    return create_token_response(user)


@router.post('/auth/login', response_model=Token)
async def login_json(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
):
    enforce_http_rate_limit(
        request,
        scope="auth.login",
        limit=settings.rate_limit_auth_per_minute,
        key_suffix=body.phone,
    )
    user = await authenticate_user(session, body.phone, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Incorrect credentials')
    return create_token_response(user)


@router.get('/auth/me', response_model=UserRead)
async def auth_me(current_user: User = Depends(get_current_user)) -> UserRead:
    roles = [UserRole(role) for role in sorted(user_role_values(current_user))]
    return UserRead(
        id=current_user.id,
        name=current_user.name,
        phone=current_user.phone,
        email=current_user.email,
        role=current_user.role,
        roles=roles,
        is_active=current_user.is_active,
    )


@router.get('/auth/users', response_model=list[UserRead])
async def auth_users(
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_only,
) -> list[UserRead]:
    users = (await session.scalars(select(User).order_by(User.name.asc(), User.phone.asc()))).all()
    payload: list[UserRead] = []
    for user in users:
        roles = [UserRole(role) for role in sorted(user_role_values(user))]
        payload.append(UserRead(
            id=user.id,
            name=user.name,
            phone=user.phone,
            email=user.email,
            role=user.role,
            roles=roles,
            is_active=user.is_active,
        ))
    return payload


@router.patch('/auth/users/{user_id}/roles', response_model=UserRead)
async def update_user_roles(
    user_id: UUID,
    body: UserRoleUpdate,
    session: AsyncSession = Depends(get_session),
    _: User = dispatcher_only,
) -> UserRead:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    extras = [role.value for role in body.additional_roles if role != body.role]
    user.role = body.role
    user.additional_roles = ",".join(sorted(set(extras))) or None
    user.is_active = body.is_active
    session.add(user)
    await session.commit()
    await session.refresh(user)
    roles = [UserRole(role) for role in sorted(user_role_values(user))]
    return UserRead(
        id=user.id,
        name=user.name,
        phone=user.phone,
        email=user.email,
        role=user.role,
        roles=roles,
        is_active=user.is_active,
    )

@router.post('/users', response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    user_in: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> User:
    enforce_http_rate_limit(
        request,
        scope="auth.register",
        limit=settings.rate_limit_register_per_minute,
        key_suffix=user_in.phone,
    )
    existing = await get_user_by_phone(session, user_in.phone)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Phone already registered')
    user = User(
        name=user_in.name,
        phone=user_in.phone,
        email=user_in.email,
        role=user_in.role,
        additional_roles=",".join(role.value for role in user_in.additional_roles if role != user_in.role) or None,
        password_hash=get_password_hash(user_in.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    roles = [UserRole(role) for role in sorted(user_role_values(user))]
    return UserRead(
        id=user.id,
        name=user.name,
        phone=user.phone,
        email=user.email,
        role=user.role,
        roles=roles,
        is_active=user.is_active,
    )
