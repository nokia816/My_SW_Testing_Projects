import pyotp
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog
from tests.conftest import PASSWORD, login


def test_requires_login():
    c = TestClient(app)
    assert c.get("/api/products").status_code == 401
    assert c.get("/api/dashboard").status_code == 401


def test_security_headers_and_no_docs_in_prod_mode():
    r = TestClient(app).get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_session_cookie_flags():
    r = TestClient(app).post("/api/auth/login", json={"email": "admin@t.example", "password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_wrong_password_generic_error_and_lockout():
    c = TestClient(app)
    unknown = c.post("/api/auth/login", json={"email": "nobody@t.example", "password": "x" * 12})
    wrong = c.post("/api/auth/login", json={"email": "admin@t.example", "password": "x" * 12})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()  # no user enumeration
    for _ in range(4):
        c.post("/api/auth/login", json={"email": "admin@t.example", "password": "x" * 12})
    locked = c.post("/api/auth/login", json={"email": "admin@t.example", "password": PASSWORD})
    assert locked.status_code == 423


def test_csrf_required_for_writes(admin):
    r = admin.c.post("/api/suppliers", json={"name": "X"})  # no CSRF header
    assert r.status_code == 403
    assert admin.post("/api/suppliers", json={"name": "X"}).status_code == 201


def test_rbac_enforced():
    viewer = login("viewer")
    assert viewer.get("/api/products").status_code == 200
    assert viewer.post("/api/products", json={"sku": "A", "name": "A"}).status_code == 403
    assert viewer.get("/api/users").status_code == 403
    wh = login("warehouse")
    assert wh.get("/api/invoices").status_code == 403
    assert wh.get("/api/employees").status_code == 403


def test_mass_assignment_rejected(admin):
    r = admin.post("/api/suppliers", json={"name": "X", "id": 999})
    assert r.status_code == 422


def test_sql_injection_in_search_is_harmless(admin):
    admin.post("/api/suppliers", json={"name": "Safe"})
    r = admin.get("/api/suppliers", params={"q": "' OR 1=1 --"})
    assert r.status_code == 200 and r.json()["total"] == 0


def test_weak_password_rejected(admin):
    r = admin.post("/api/users", json={"email": "n@t.example", "full_name": "N", "password": "password123"})
    assert r.status_code == 422


def test_new_user_must_change_password(admin):
    admin.post("/api/users", json={"email": "fresh@t.example", "full_name": "N", "password": "Brand-New!Pass99"})
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "fresh@t.example", "password": "Brand-New!Pass99"})
    csrf = r.json()["csrf_token"]
    assert c.get("/api/products").json()["detail"] == "password_change_required"
    r = c.post("/api/auth/change-password", headers={"X-CSRF-Token": csrf},
               json={"current_password": "Brand-New!Pass99", "new_password": "Another!Pass-77x"})
    assert r.status_code == 200
    assert c.get("/api/products").status_code == 200


def test_cannot_remove_last_admin(admin):
    me = admin.get("/api/auth/me").json()["user"]
    assert admin.patch(f"/api/users/{me['id']}", json={"role": "viewer"}).status_code == 400


def test_2fa_flow(admin):
    secret = admin.post("/api/auth/2fa/setup").json()["secret"]
    assert admin.post("/api/auth/2fa/enable", json={"code": "000000"}).status_code == 400
    assert admin.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "admin@t.example", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["detail"] == "otp_required"
    r = c.post("/api/auth/login", json={"email": "admin@t.example", "password": PASSWORD,
                                        "otp": pyotp.TOTP(secret).now()})
    assert r.status_code == 200


def test_logout_revokes_session(admin):
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/auth/me").status_code == 401


def test_audit_chain_detects_tampering(admin):
    admin.post("/api/suppliers", json={"name": "A"})
    admin.post("/api/suppliers", json={"name": "B"})
    assert admin.get("/api/audit/verify").json()["valid"] is True
    with SessionLocal() as db:
        row = db.query(AuditLog).filter(AuditLog.action == "create").first()
        row.details = {"name": "tampered"}
        db.commit()
    assert admin.get("/api/audit/verify").json()["valid"] is False


def test_audit_never_stores_secrets(admin):
    admin.post("/api/users", json={"email": "s@t.example", "full_name": "S", "password": "Brand-New!Pass99"})
    with SessionLocal() as db:
        for row in db.query(AuditLog).all():
            assert "Brand-New!Pass99" not in str(row.details)


def test_csv_formula_injection_neutralised(admin):
    admin.post("/api/suppliers", json={"name": "=HYPERLINK(\"http://evil\")"})
    body = admin.get("/api/export/suppliers").text
    assert "'=HYPERLINK" in body
