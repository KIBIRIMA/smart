"""Routes d'authentification : login (JWT), refresh, profil courant."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.security import (create_access_token, create_refresh_token,
                               decode_token, verify_password)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import TokenPair, RefreshRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # OAuth2PasswordRequestForm utilise le champ "username" → on y met l'email
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte désactivé")
    return TokenPair(
        access_token=create_access_token(user.email, user.role),
        refresh_token=create_refresh_token(user.email, user.role),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalide")
        email = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token de rafraîchissement invalide")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utilisateur introuvable")
    return TokenPair(
        access_token=create_access_token(user.email, user.role),
        refresh_token=create_refresh_token(user.email, user.role),
    )


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
