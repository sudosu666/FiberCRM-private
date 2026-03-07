from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..schemas import Token, UserCreate, UserRead
from .auth_helpers import (
    authenticate_user,
    create_token_response,
    get_password_hash,
    get_user_by_phone,
)
from .database import get_session

router = APIRouter(prefix='')

@router.post('/token', response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    user = await authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Incorrect credentials')
    return create_token_response(user)

@router.post('/users', response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, session: AsyncSession = Depends(get_session)) -> User:
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
