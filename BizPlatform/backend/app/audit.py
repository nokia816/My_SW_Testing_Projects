"""Hash-chained audit log: each row's hash covers the previous row's hash, so any edit/delete is detectable."""
import hashlib
import json
import threading
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, User, utcnow

GENESIS = "0" * 64
_lock = threading.Lock()
SENSITIVE = {"password", "password_hash", "totp_secret", "national_id", "license_key", "code", "new_password",
             "current_password"}


def _default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return str(o)
    if hasattr(o, "value"):
        return o.value
    return str(o)


def scrub(data: dict | None) -> dict | None:
    if data is None:
        return None
    return {k: ("***" if k in SENSITIVE else v) for k, v in data.items()}


def _digest(row: AuditLog) -> str:
    ts = row.ts if row.ts.tzinfo else row.ts.replace(tzinfo=timezone.utc)
    ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    payload = json.dumps({"ts": ts.isoformat(timespec="microseconds"),
                          "user_id": row.user_id, "action": row.action,
                          "entity": row.entity, "entity_id": row.entity_id, "details": row.details, "ip": row.ip,
                          "prev": row.prev_hash}, sort_keys=True, default=_default, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def record(db: Session, user: User | None, action: str, entity: str, entity_id=None, details: dict | None = None,
           ip: str | None = None, commit: bool = True) -> None:
    with _lock:
        last = db.execute(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)).scalar()
        row = AuditLog(ts=utcnow(), user_id=user.id if user else None,
                       user_email=user.email if user else None, action=action, entity=entity,
                       entity_id=str(entity_id) if entity_id is not None else None,
                       details=json.loads(json.dumps(scrub(details), default=_default)) if details else None,
                       ip=ip, prev_hash=last or GENESIS)
        row.hash = _digest(row)
        db.add(row)
        if commit:
            db.commit()


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for row in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
        if row.prev_hash != prev or _digest(row) != row.hash:
            return {"valid": False, "broken_at_id": row.id, "checked": count}
        prev = row.hash
        count += 1
    return {"valid": True, "checked": count}
