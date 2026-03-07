from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_access_token, decode_token, verify_password
from ..config import settings
from ..database import get_session
from ..models import User
from ..schemas import Token, TokenData, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')


def create_token_response(user: User) -> Token:
    expires = timedelta(minutes=settings.access_token_expire_minutes)
    token = create_access_token({'sub': user.phone, 'role': user.role.value}, expires_delta=expires)
    return Token(access_token=token)


async def get_user_by_phone(session: AsyncSession, phone: str) -> Optional[User]:
    stmt = select(User).where(User.phone == phone)
    result = await session.execute(stmt)
    return result.scalars().first()


async def authenticate_user(session: AsyncSession, phone: str, password: str) -> Optional[User]:
    user = await get_user_by_phone(session, phone)
    if user and verify_password(password, user.password_hash):
        return user
    return None


async def get_current_user(token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)) -> User:
    try:
        payload = decode_token(token)
        phone = payload.phone
        if not phone:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid authentication')
        user = await get_user_by_phone(session, phone)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')
        return user
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token invalid or expired') from exc


async def require_role(role: UserRole, current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient rights')
    return current_user
