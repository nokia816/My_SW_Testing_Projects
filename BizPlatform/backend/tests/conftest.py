import os
import tempfile

from cryptography.fernet import Fernet

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ.setdefault("BIZ_DATABASE_URL", f"sqlite:///{_db}")
os.environ.update(BIZ_ENV="test", BIZ_COOKIE_SECURE="false",
                  BIZ_ENCRYPTION_KEY=Fernet.generate_key().decode(), BIZ_LOGIN_RATE_PER_MINUTE="1000")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.security import hash_password, rate_limiter  # noqa: E402

PASSWORD = "Test!Passw0rd-123"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    rate_limiter.reset()
    with SessionLocal() as db:
        for role in Role:
            db.add(User(email=f"{role.value}@t.example", full_name=role.value, role=role,
                        password_hash=hash_password(PASSWORD)))
        db.commit()
    yield


class Api:
    def __init__(self, client: TestClient, csrf: str):
        self.c, self.csrf = client, csrf

    def __getattr__(self, method):
        def call(url, **kw):
            headers = kw.pop("headers", {})
            headers.setdefault("X-CSRF-Token", self.csrf)
            return getattr(self.c, method)(url, headers=headers, **kw)
        return call


def login(role: str = "admin") -> Api:
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"email": f"{role}@t.example", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return Api(client, r.json()["csrf_token"])


@pytest.fixture
def admin() -> Api:
    return login("admin")
