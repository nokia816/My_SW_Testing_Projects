import io

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import SESSION_COOKIE, client_ip, current_user, get_session
from ..models import User, UserSession
from ..schemas import ChangePasswordIn, LoginIn, OtpIn, UserOut
from ..security import (PERMISSIONS, aware, hash_password, lock_expiry, new_token, new_totp_secret, now_utc,
                        password_problems, rate_limiter, token_hash, totp_uri, verify_password, verify_totp)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _me(user: User, sess: UserSession) -> dict:
    settings = get_settings()
    perms = {res: sorted(a for a, roles in acts.items() if user.role in roles) for res, acts in PERMISSIONS.items()}
    return {"user": UserOut.model_validate(user).model_dump(mode="json"), "csrf_token": sess.csrf_token,
            "permissions": perms, "require_2fa": settings.require_2fa, "org_name": settings.org_name,
            "vat_rate": settings.vat_rate}


@router.post("/login")
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    ip = client_ip(request) or "?"
    email = data.email.lower()
    if not rate_limiter.allow(f"login:{ip}", settings.login_rate_per_minute) or \
            not rate_limiter.allow(f"login-user:{email}", settings.login_rate_per_minute):
        raise HTTPException(429, "יותר מדי ניסיונות. נסה שוב בעוד דקה")
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    generic = HTTPException(401, "אימייל או סיסמה שגויים")
    if user and user.locked_until and aware(user.locked_until) > now_utc():
        audit.record(db, user, "login_locked", "auth", user.id, None, ip)
        raise HTTPException(423, "החשבון נעול זמנית עקב ניסיונות כושלים")
    ok = verify_password(data.password, user.password_hash if user else None)
    if not user or not ok or not user.is_active:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.locked_until = lock_expiry(settings.lockout_minutes)
                user.failed_logins = 0
            db.commit()
        audit.record(db, user, "login_failed", "auth", user.id if user else None, {"email": email}, ip)
        raise generic
    if user.totp_enabled:
        if not data.otp:
            raise HTTPException(401, "otp_required")
        if not verify_totp(user.totp_secret, data.otp):
            user.failed_logins += 1
            db.commit()
            audit.record(db, user, "login_failed_otp", "auth", user.id, None, ip)
            raise HTTPException(401, "קוד אימות שגוי")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now_utc()
    token = new_token()
    sess = UserSession(token_hash=token_hash(token), csrf_token=new_token(), user_id=user.id, ip=ip,
                       user_agent=(request.headers.get("user-agent") or "")[:300])
    db.add(sess)
    db.commit()
    audit.record(db, user, "login", "auth", user.id, None, ip)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="strict",
                        max_age=settings.session_absolute_hours * 3600, path="/")
    return _me(user, sess)


@router.post("/logout")
def logout(request: Request, response: Response, sess: UserSession = Depends(get_session),
           db: Session = Depends(get_db)):
    user = sess.user
    db.delete(sess)
    db.commit()
    audit.record(db, user, "logout", "auth", user.id, None, client_ip(request))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    audit.record(db, user, "logout_all", "auth", user.id, None, client_ip(request))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(sess: UserSession = Depends(get_session), user: User = Depends(current_user)):
    return _me(user, sess)


@router.post("/change-password")
def change_password(data: ChangePasswordIn, request: Request, sess: UserSession = Depends(get_session),
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "הסיסמה הנוכחית שגויה")
    problems = password_problems(data.new_password, user.email)
    if verify_password(data.new_password, user.password_hash):
        problems.append("הסיסמה החדשה זהה לישנה")
    if problems:
        raise HTTPException(422, problems)
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    # revoke all other sessions
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.id != sess.id))
    db.commit()
    audit.record(db, user, "password_changed", "auth", user.id, None, client_ip(request))
    return {"ok": True}


@router.post("/2fa/setup")
def totp_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(400, "אימות דו-שלבי כבר פעיל")
    user.totp_secret = new_totp_secret()
    db.commit()
    uri = totp_uri(user.totp_secret, user.email, get_settings().org_name)
    buf = io.BytesIO()
    qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).save(buf)
    return {"secret": user.totp_secret, "otpauth_uri": uri, "qr_svg": buf.getvalue().decode()}


@router.post("/2fa/enable")
def totp_enable(data: OtpIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_totp(user.totp_secret, data.code):
        raise HTTPException(400, "קוד שגוי")
    user.totp_enabled = True
    db.commit()
    audit.record(db, user, "2fa_enabled", "auth", user.id, None, client_ip(request))
    return {"ok": True}


@router.post("/2fa/disable")
def totp_disable(data: OtpIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if get_settings().require_2fa:
        raise HTTPException(400, "מדיניות הארגון מחייבת אימות דו-שלבי")
    if not verify_totp(user.totp_secret, data.code):
        raise HTTPException(400, "קוד שגוי")
    user.totp_enabled = False
    user.totp_secret = None
    db.commit()
    audit.record(db, user, "2fa_disabled", "auth", user.id, None, client_ip(request))
    return {"ok": True}
