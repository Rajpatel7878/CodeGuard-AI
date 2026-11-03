"""Authentication API routes."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.limits import limiter
from app.config import settings
from app.database.models import PasswordResetToken, User
from app.database.session import get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes from SQLite as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserRegister, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    user = User(
        id=f"usr_{uuid4().hex[:12]}",
        full_name=user_data.full_name,
        email=user_data.email,
        password_hash=AuthService.get_password_hash(user_data.password),
        provider="email",
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent signups for the same address: the unique index wins.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    db.refresh(user)

    # Create access token
    access_token = AuthService.create_access_token(data={"sub": user.email})

    response = Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )
    return response


@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(request: Request, user_data: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not AuthService.verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    access_token = AuthService.create_access_token(data={"sub": user.email})

    # Set secure cookie if remember_me or in production
    if user_data.remember_me or settings.environment != "development":
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.environment != "development",
            samesite="lax",
            max_age=settings.access_token_expire_minutes * 60,
        )

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("session")
    return MessageResponse(message="Successfully logged out")


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    # Always return generic response to prevent account enumeration
    if user:
        # Delete any existing tokens for this user
        db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete()

        # Generate token
        token = AuthService.generate_reset_token()
        token_hash = AuthService.hash_reset_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        reset_token = PasswordResetToken(
            id=f"rst_{uuid4().hex[:12]}",
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(reset_token)
        db.commit()

        # No email provider is configured, so the token is intentionally not
        # logged or returned. Delivering reset mail is a documented limitation.

    return MessageResponse(message="If an account with that email exists, a password reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordRequest, db: Session = Depends(get_db)):
    # Find a matching, unexpired token. Expiry is compared in Python so the
    # check does not depend on how the database stores timezone offsets.
    now = datetime.now(timezone.utc)
    tokens = db.query(PasswordResetToken).filter(PasswordResetToken.used == False).all()  # noqa: E712

    valid_token = None
    for candidate in tokens:
        if _as_utc(candidate.expires_at) <= now:
            continue
        if AuthService.verify_reset_token(data.token, candidate.token_hash):
            valid_token = candidate
            break

    if not valid_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user = db.query(User).filter(User.id == valid_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User not found",
        )

    # Update password
    user.password_hash = AuthService.get_password_hash(data.password)
    valid_token.used = True
    db.commit()

    return MessageResponse(message="Password has been reset successfully")


# Google OAuth
@router.get("/google/login")
async def google_login():
    state = secrets.token_urlsafe(32)
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.google_client_id}&"
        f"redirect_uri={settings.google_redirect_uri}&"
        f"scope=openid%20email%20profile&"
        f"response_type=code&"
        f"state={state}"
    )
    response = RedirectResponse(url=auth_url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=600, samesite="lax")
    return response


@router.get("/google/callback")
async def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")

    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google OAuth not configured")

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
        )
        if token_response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exchange code")
        token_data = token_response.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing ID token from Google",
            )

        # Google validates the signature and expiry for us; we still have to
        # check the audience so a token minted for another client is rejected.
        info_response = await client.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": id_token},
            timeout=10.0,
        )
        if info_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google ID token",
            )
        decoded = info_response.json()

        if decoded.get("aud") != settings.google_client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google token was issued for a different application",
            )
        if decoded.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google token issuer",
            )

        google_id = decoded.get("sub")
        email = decoded.get("email")
        name = decoded.get("name", "")
        picture = decoded.get("picture")

        if not google_id or not email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user info")

        # Find or create user
        user = db.query(User).filter(User.google_id == google_id).first()
        if not user:
            # Check if email exists
            user = db.query(User).filter(User.email == email).first()
            if user:
                # Link account
                user.google_id = google_id
                user.provider = "google" if user.provider == "email" else user.provider
            else:
                user = User(
                    id=f"usr_{uuid4().hex[:12]}",
                    full_name=name,
                    email=email,
                    profile_picture=picture,
                    provider="google",
                    google_id=google_id,
                    is_active=True,
                    is_verified=True,
                )
                db.add(user)
        db.commit()
        db.refresh(user)

        # Create token and redirect
        access_token = AuthService.create_access_token(data={"sub": user.email})
        response = RedirectResponse(url=f"{settings.frontend_url}/auth/callback?token={access_token}")
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=settings.environment != "development", samesite="lax")
        return response


# GitHub OAuth
@router.get("/github/login")
async def github_login():
    state = secrets.token_urlsafe(32)
    auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={settings.github_client_id}&"
        f"redirect_uri={settings.github_redirect_uri}&"
        f"scope=user:email&"
        f"state={state}"
    )
    response = RedirectResponse(url=auth_url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=600, samesite="lax")
    return response


@router.get("/github/callback")
async def github_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")

    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="GitHub OAuth not configured")

    async with httpx.AsyncClient() as client:
        # Exchange code for token
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
        )
        if token_response.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exchange code")
        token_data = token_response.json()
        access_token_github = token_data.get("access_token")

        if not access_token_github:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No access token")

        # Get user info
        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token_github}", "User-Agent": "AlphaCodeGuard"},
        )
        user_data = user_response.json()

        github_id = str(user_data.get("id"))
        name = user_data.get("name") or user_data.get("login", "")
        picture = user_data.get("avatar_url")

        # Get primary email
        email_response = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token_github}", "User-Agent": "AlphaCodeGuard"},
        )
        emails = email_response.json()
        if not isinstance(emails, list):
            emails = []
        primary_email = None
        for e in emails:
            if e.get("primary") and e.get("verified"):
                primary_email = e.get("email")
                break
        if not primary_email and emails:
            primary_email = emails[0].get("email")

        if not github_id or not primary_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing user info")

        # Find or create user
        user = db.query(User).filter(User.github_id == github_id).first()
        if not user:
            user = db.query(User).filter(User.email == primary_email).first()
            if user:
                user.github_id = github_id
                user.provider = "github" if user.provider == "email" else user.provider
            else:
                user = User(
                    id=f"usr_{uuid4().hex[:12]}",
                    full_name=name,
                    email=primary_email,
                    profile_picture=picture,
                    provider="github",
                    github_id=github_id,
                    is_active=True,
                    is_verified=True,
                )
                db.add(user)
        db.commit()
        db.refresh(user)

        access_token = AuthService.create_access_token(data={"sub": user.email})
        response = RedirectResponse(url=f"{settings.frontend_url}/auth/callback?token={access_token}")
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=settings.environment != "development", samesite="lax")
        return response
