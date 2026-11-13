from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import client_ip, require
from ..models import Role, User, UserSession
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import hash_password, password_problems
from .crud import commit_or_409, get_or_404

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
def list_users(db: Session = Depends(get_db), _: User = Depends(require("users"))):
    rows = db.execute(select(User).order_by(User.id)).scalars().all()
    return {"total": len(rows), "items": [UserOut.model_validate(u) for u in rows]}


@router.post("", status_code=201)
def create_user(data: UserCreate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require("users", "write"))):
    problems = password_problems(data.password, data.email)
    if problems:
        raise HTTPException(422, problems)
    user = User(email=data.email.lower(), full_name=data.full_name, role=data.role,
                password_hash=hash_password(data.password), must_change_password=True)
    db.add(user)
    commit_or_409(db)
    audit.record(db, admin, "create", "users", user.id, {"email": user.email, "role": user.role}, client_ip(request))
    return UserOut.model_validate(user)


@router.patch("/{user_id}")
def update_user(user_id: int, data: UserUpdate, request: Request, db: Session = Depends(get_db),
                admin: User = Depends(require("users", "write"))):
    user = get_or_404(db, User, user_id)
    values = data.model_dump(exclude_unset=True)
    demoting_admin = user.role == Role.admin and (values.get("role", Role.admin) != Role.admin
                                                  or values.get("is_active") is False)
    if demoting_admin:
        admins = db.execute(select(func.count()).where(User.role == Role.admin, User.is_active.is_(True))).scalar()
        if admins <= 1:
            raise HTTPException(400, "לא ניתן להסיר את המנהל האחרון במערכת")
    changes = {}
    for key in ("full_name", "role", "is_active"):
        if key in values and values[key] is not None:
            changes[key] = values[key]
            setattr(user, key, values[key])
    if values.get("reset_password"):
        problems = password_problems(values["reset_password"], user.email)
        if problems:
            raise HTTPException(422, problems)
        user.password_hash = hash_password(values["reset_password"])
        user.must_change_password = True
        user.locked_until = None
        changes["password"] = "reset"
    if values.get("reset_2fa"):
        user.totp_enabled = False
        user.totp_secret = None
        changes["2fa"] = "reset"
    if values.get("is_active") is False or "password" in changes or values.get("role"):
        db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    commit_or_409(db)
    audit.record(db, admin, "update", "users", user.id, changes, client_ip(request))
    return UserOut.model_validate(user)
