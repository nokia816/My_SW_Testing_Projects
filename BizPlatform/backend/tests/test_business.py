from datetime import date, timedelta

from app.db import SessionLocal
from sqlalchemy import text
from tests.conftest import login


def _setup_stock(admin):
    w1 = admin.post("/api/warehouses", json={"name": "Main"}).json()["id"]
    w2 = admin.post("/api/warehouses", json={"name": "North"}).json()["id"]
    p = admin.post("/api/products", json={"sku": "SKU1", "name": "Mouse", "cost_price": "10", "sale_price": "25",
                                          "min_stock": 5}).json()["id"]
    return w1, w2, p


def test_stock_movements_and_no_negative_stock(admin):
    w1, w2, p = _setup_stock(admin)
    assert admin.post("/api/stock/movements", json={"product_id": p, "warehouse_id": w1, "type": "receive",
                                                    "quantity": 10}).status_code == 201
    r = admin.post("/api/stock/movements", json={"product_id": p, "warehouse_id": w1, "type": "issue", "quantity": 11})
    assert r.status_code == 409
    admin.post("/api/stock/movements", json={"product_id": p, "warehouse_id": w1, "type": "transfer", "quantity": 4,
                                             "to_warehouse_id": w2})
    levels = {lv["warehouse_id"]: lv["quantity"] for lv in admin.get("/api/stock/levels").json()}
    assert levels == {w1: 6, w2: 4}
    assert admin.get(f"/api/products/{p}").json()["stock"] == 10


def test_duplicate_sku_conflict(admin):
    admin.post("/api/products", json={"sku": "DUP", "name": "A"})
    assert admin.post("/api/products", json={"sku": "DUP", "name": "B"}).status_code == 409


def test_invoice_tracking_vat_payments_and_status(admin):
    c = admin.post("/api/customers", json={"name": "Acme", "payment_terms_days": 30}).json()["id"]
    inv = admin.post("/api/invoices", json={"number": "1001", "customer_id": c, "issue_date": str(date.today()),
                                            "amount_before_vat": "10000"}).json()
    assert inv["vat_amount"] == "1800.00" and inv["total"] == "11800.00"
    assert inv["due_date"] == str(date.today() + timedelta(days=30))
    assert inv["allocation_required"] is True  # >= 5,000 ILS without allocation number
    assert admin.post(f"/api/invoices/{inv['id']}/payments", json={"paid_on": str(date.today()),
                                                                   "amount": "99999"}).status_code == 422
    r = admin.post(f"/api/invoices/{inv['id']}/payments", json={"paid_on": str(date.today()), "amount": "5000"}).json()
    assert r["status"] == "partial" and r["balance"] == "6800.00"
    r = admin.post(f"/api/invoices/{inv['id']}/payments", json={"paid_on": str(date.today()), "amount": "6800"}).json()
    assert r["status"] == "paid"
    r = admin.patch(f"/api/invoices/{inv['id']}", json={"allocation_number": "987654321"}).json()
    assert r["allocation_required"] is False
    assert admin.delete(f"/api/invoices/{inv['id']}").status_code == 409  # has payments


def test_overdue_detection(admin):
    c = admin.post("/api/customers", json={"name": "Late"}).json()["id"]
    admin.post("/api/invoices", json={"number": "9", "customer_id": c, "issue_date": str(date.today() - timedelta(90)),
                                      "amount_before_vat": "100"})
    r = admin.get("/api/invoices", params={"overdue": "true"}).json()
    assert r["total"] == 1 and r["items"][0]["overdue"] is True
    assert admin.get("/api/dashboard").json()["finance"]["overdue_count"] == 1


def _employee(admin, num="E1"):
    return admin.post("/api/employees", json={"employee_number": num, "first_name": "Dana", "last_name": "Cohen",
                                              "national_id": "123456782"}).json()["id"]


def test_national_id_encrypted_and_need_to_know(admin):
    eid = _employee(admin)
    assert admin.get(f"/api/employees/{eid}").json()["national_id"] == "123456782"
    assert login("it").get(f"/api/employees/{eid}").json()["national_id"] is None
    with SessionLocal() as db:
        raw = db.execute(text("SELECT national_id FROM employees")).scalar()
        assert raw != "123456782" and len(raw) > 50  # stored encrypted


def test_asset_lifecycle_and_offboarding(admin):
    eid = _employee(admin)
    a = admin.post("/api/assets", json={"asset_tag": "LT-1", "type": "laptop", "license_key": "SECRET"}).json()
    assert a["status"] == "in_stock" and a["license_key"] is None and a["has_license_key"] is True
    assert admin.get(f"/api/assets/{a['id']}/secret").json()["license_key"] == "SECRET"
    assert login("viewer").get(f"/api/assets/{a['id']}/secret").status_code == 403
    r = admin.post(f"/api/assets/{a['id']}/assign", json={"employee_id": eid, "condition": "new"}).json()
    assert r["status"] == "assigned" and r["employee_name"] == "Dana Cohen"
    assert admin.post(f"/api/assets/{a['id']}/assign", json={"employee_id": eid}).status_code == 409
    off = admin.post(f"/api/employees/{eid}/offboard").json()
    assert [x["asset_tag"] for x in off["assets_to_return"]] == ["LT-1"]
    assert admin.get("/api/dashboard").json()["assets"]["offboarding"][0]["assets_to_return"] == 1
    # can't close employee while holding equipment
    assert admin.patch(f"/api/employees/{eid}", json={"status": "left"}).status_code == 409
    admin.post(f"/api/assets/{a['id']}/return", json={"condition": "scratched"})
    assert admin.patch(f"/api/employees/{eid}", json={"status": "left"}).status_code == 200
    hist = admin.get(f"/api/assets/{a['id']}/history").json()
    assert hist[0]["condition_out"] == "new" and hist[0]["condition_in"] == "scratched" and hist[0]["returned_at"]
    assert admin.delete(f"/api/employees/{eid}").status_code == 409  # keep custody history


def test_dashboard_scoped_by_role(admin):
    d = login("warehouse").get("/api/dashboard").json()
    assert "inventory" in d and "finance" not in d and "assets" not in d
