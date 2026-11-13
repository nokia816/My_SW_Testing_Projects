import hmac
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User, UserSession
from .security import aware, can, now_utc, token_hash

SESSION_COOKIE = "biz_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def get_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    settings = get_settings()
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "לא מחובר")
    sess = db.execute(select(UserSession).where(UserSession.token_hash == token_hash(token))).scalar_one_or_none()
    now = now_utc()
    if (sess is None or not sess.user.is_active
            or now - aware(sess.last_seen_at) > timedelta(minutes=settings.session_idle_minutes)
            or now - aware(sess.created_at) > timedelta(hours=settings.session_absolute_hours)):
        if sess is not None:
            db.delete(sess)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "פג תוקף ההתחברות")
    # CSRF: synchronizer token required on every state-changing request
    if request.method in UNSAFE:
        header = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(header, sess.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token invalid")
    if (now - aware(sess.last_seen_at)).total_seconds() > 30:
        sess.last_seen_at = now
        db.commit()
    return sess


def current_user(request: Request, sess: UserSession = Depends(get_session)) -> User:
    user = sess.user
    settings = get_settings()
    path = request.url.path
    # Users forced to change password / enable 2FA can only reach the account endpoints
    if not path.startswith("/api/auth/"):
        if user.must_change_password:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "password_change_required")
        if settings.require_2fa and not user.totp_enabled:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "2fa_setup_required")
    return user


def require(resource: str, action: str = "read"):
    def checker(user: User = Depends(current_user)) -> User:
        if not can(user.role, resource, action):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "אין הרשאה לפעולה זו")
        return user
    return checker
