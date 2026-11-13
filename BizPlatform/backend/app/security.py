"""Password hashing, session tokens, TOTP 2FA, rate limiting and role-based permissions."""
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .models import Role

# OWASP recommended Argon2id parameters
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
# Constant-time dummy hash so unknown e-mails take as long as wrong passwords (no user enumeration)
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))

_COMMON = {"password", "123456", "12345678", "123456789", "qwerty", "111111", "password1", "admin", "welcome",
           "letmein", "iloveyou", "1234567890", "qwertyuiop", "abc123", "passw0rd", "changeme", "Aa123456"}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    try:
        return _ph.verify(hashed or _DUMMY_HASH, password) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problems(password: str, email: str = "") -> list[str]:
    problems = []
    if len(password) < 12:
        problems.append("הסיסמה חייבת להכיל לפחות 12 תווים")
    if len(password) > 128:
        problems.append("הסיסמה ארוכה מדי")
    classes = sum([any(c.islower() for c in password), any(c.isupper() for c in password),
                   any(c.isdigit() for c in password), any(not c.isalnum() for c in password)])
    if classes < 3:
        problems.append("הסיסמה צריכה לשלב לפחות 3 מתוך: אותיות קטנות, גדולות, ספרות, סימנים")
    if password.lower() in {p.lower() for p in _COMMON}:
        problems.append("סיסמה נפוצה מדי")
    if email and email.split("@")[0].lower() in password.lower():
        problems.append("הסיסמה לא יכולה להכיל את שם המשתמש")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------- TOTP
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str | None, code: str | None) -> bool:
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    return code.isdigit() and pyotp.TOTP(secret).verify(code, valid_window=1)


# ---------------------------------------------------------------- rate limiting (per-process sliding window)
class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: int = 60) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalise to UTC-aware."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def lock_expiry(minutes: int) -> datetime:
    return now_utc() + timedelta(minutes=minutes)


# ---------------------------------------------------------------- RBAC
R = Role
ALL = set(Role)
PERMISSIONS: dict[str, dict[str, set[Role]]] = {
    "suppliers": {"read": ALL, "write": {R.admin, R.manager, R.warehouse, R.finance, R.it}},
    "customers": {"read": {R.admin, R.manager, R.finance, R.warehouse, R.viewer}, "write": {R.admin, R.manager, R.finance}},
    "warehouses": {"read": ALL, "write": {R.admin, R.manager, R.warehouse}},
    "products": {"read": ALL, "write": {R.admin, R.manager, R.warehouse}},
    "stock": {"read": ALL, "write": {R.admin, R.manager, R.warehouse}},
    "invoices": {"read": {R.admin, R.manager, R.finance, R.viewer}, "write": {R.admin, R.manager, R.finance}},
    "departments": {"read": ALL, "write": {R.admin, R.manager, R.hr}},
    "employees": {"read": {R.admin, R.manager, R.hr, R.it, R.viewer}, "write": {R.admin, R.manager, R.hr}},
    # sensitive personal data (national ID) – only HR/admin
    "employees_pii": {"read": {R.admin, R.hr}, "write": {R.admin, R.hr}},
    "assets": {"read": {R.admin, R.manager, R.it, R.hr, R.viewer}, "write": {R.admin, R.manager, R.it}},
    "asset_secrets": {"read": {R.admin, R.it}, "write": {R.admin, R.it}},
    "dashboard": {"read": ALL, "write": set()},
    "users": {"read": {R.admin}, "write": {R.admin}},
    "audit": {"read": {R.admin}, "write": set()},
}


def can(role: Role, resource: str, action: str) -> bool:
    return role in PERMISSIONS.get(resource, {}).get(action, set())
