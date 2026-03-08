from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..auth import get_password_hash
from ..rate_limit import enforce_http_rate_limit
from ..models import User
from ..schemas import LoginRequest, Token, UserCreate, UserRead
from .auth_helpers import (
    authenticate_user,
    create_token_response,
    get_current_user,
    get_user_by_phone,
)
from ..database import get_session

router = APIRouter(prefix='')

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
async def auth_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user

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
        password_hash=get_password_hash(user_in.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
