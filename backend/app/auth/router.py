from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.auth.schemas import (
    ChangePasswordIn, ForgotPasswordIn, LoginIn, ProfileUpdateIn, RefreshIn, ResetPasswordIn, TokenOut,
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.core.rate_limit import rate_limiter
from app.core.schemas import Message
from app.core.security import (
    _create_token, create_access_token, create_refresh_token, decode_token, hash_password, verify_password,
)
from app.database.base import utcnow
from app.database.session import get_db
from app.services.email import send_templated
from app.users.models import User
from app.users.schemas import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "token_type": "bearer",
        "user": user,
    }


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limiter("login", 20))])
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError("Invalid email or password", 401)
    if not user.is_active:
        raise AppError("This account has been deactivated", 403)
    user.last_login_at = utcnow()
    audit(db, user.id, "login", "user", user.id, ip_address=request.client.host if request.client else None)
    db.commit()
    return _token_response(user)


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(rate_limiter("refresh", 60))])
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    data = decode_token(payload.refresh_token, "refresh")
    if not data:
        raise AppError("Invalid or expired refresh token", 401)
    user = db.get(User, data["sub"])
    if not user or not user.is_active:
        raise AppError("Invalid or expired refresh token", 401)
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_profile(payload: ProfileUpdateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    return user


@router.post("/change-password", response_model=Message)
def change_password(payload: ChangePasswordIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        raise AppError("Current password is incorrect", 400)
    user.password_hash = hash_password(payload.new_password)
    audit(db, user.id, "change_password", "user", user.id)
    db.commit()
    return {"detail": "Password updated"}


@router.post("/forgot-password", response_model=Message, dependencies=[Depends(rate_limiter("forgot", 5))])
def forgot_password(payload: ForgotPasswordIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if user and user.is_active:
        token = _create_token(user.id, "reset", timedelta(minutes=30))
        origin = settings.public_app_url
        send_templated(db, user.email, "password_reset",
                       {"first_name": user.first_name, "reset_link": f"{origin}/reset-password?token={token}"})
    # Same response either way — do not leak which emails exist.
    return {"detail": "If that email exists, a reset link has been sent"}


@router.post("/reset-password", response_model=Message, dependencies=[Depends(rate_limiter("reset", 10))])
def reset_password(payload: ResetPasswordIn, db: Session = Depends(get_db)):
    data = decode_token(payload.token, "reset")
    if not data:
        raise AppError("Invalid or expired reset token", 400)
    user = db.get(User, data["sub"])
    if not user:
        raise AppError("Invalid or expired reset token", 400)
    user.password_hash = hash_password(payload.new_password)
    audit(db, user.id, "reset_password", "user", user.id)
    db.commit()
    return {"detail": "Password has been reset"}
