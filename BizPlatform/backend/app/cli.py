"""Admin CLI.  Usage:
    python -m app.cli create-admin --email you@company.co.il --name "Your Name"
    python -m app.cli seed-demo        # demo data (development only)
    python -m app.cli verify-audit
"""
import argparse
import getpass
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from . import audit
from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import (Asset, AssetAssignment, AssetStatus, AssetType, Customer, Department, Employee, Invoice,
                     MovementType, Payment, Product, Role, StockMovement, Supplier, User, Warehouse)
from .routers.invoices import recompute
from .security import hash_password, password_problems


def create_admin(email: str, name: str, password: str | None) -> None:
    password = password or getpass.getpass("Password (min 12 chars): ")
    problems = password_problems(password, email)
    if problems:
        sys.exit("\n".join(problems))
    with SessionLocal() as db:
        if db.execute(select(User).where(User.email == email.lower())).scalar():
            sys.exit("User already exists")
        u = User(email=email.lower(), full_name=name, role=Role.admin, password_hash=hash_password(password))
        db.add(u)
        db.commit()
        audit.record(db, None, "create_admin_cli", "users", u.id, {"email": u.email})
    print(f"Admin {email} created. Enable 2FA after first login.")


def seed_demo() -> None:
    if not get_settings().is_dev:
        sys.exit("seed-demo is only allowed with BIZ_ENV=development")
    today = date.today()
    with SessionLocal() as db:
        if db.execute(select(Product)).first():
            sys.exit("Database already has data")
        s1 = Supplier(name="טק-סאפליי בע\"מ", vat_id="514000001", phone="03-5550000", email="sales@tech.example")
        s2 = Supplier(name="אופיס פלוס", vat_id="514000002", phone="09-7770000")
        c1 = Customer(name="אלפא תעשיות", vat_id="515111111", email="ap@alpha.example", payment_terms_days=30)
        c2 = Customer(name="בטא שיווק", vat_id="515222222", payment_terms_days=60)
        c3 = Customer(name="גמא סטודיו", vat_id="515333333", payment_terms_days=0)
        w1, w2 = Warehouse(name="מחסן ראשי", location="תל אביב"), Warehouse(name="מחסן צפון", location="חיפה")
        d1, d2, d3 = Department(name="הנהלה"), Department(name="פיתוח"), Department(name="מכירות")
        db.add_all([s1, s2, c1, c2, c3, w1, w2, d1, d2, d3])
        db.flush()
        prods = [Product(sku=f"P-{i:04d}", name=n, category=c, cost_price=Decimal(cp), sale_price=Decimal(sp),
                         min_stock=m, supplier_id=s1.id if i % 2 else s2.id)
                 for i, (n, c, cp, sp, m) in enumerate([
                     ("מקלדת אלחוטית", "ציוד היקפי", "80", "149", 10), ("עכבר ארגונומי", "ציוד היקפי", "60", "119", 10),
                     ("מסך 27 אינץ'", "מסכים", "900", "1390", 3), ("כבל USB-C", "כבלים", "8", "29", 50),
                     ("נייר A4 (קרטון)", "משרדי", "95", "140", 5), ("אוזניות", "ציוד היקפי", "150", "249", 5)], 1)]
        db.add_all(prods)
        db.flush()
        for p, q in zip(prods, [40, 6, 8, 200, 3, 12]):
            db.add(StockMovement(product_id=p.id, warehouse_id=w1.id, quantity=q, type=MovementType.receive,
                                 reference="קליטה ראשונית"))
        db.add(StockMovement(product_id=prods[1].id, warehouse_id=w1.id, quantity=-2, type=MovementType.issue))
        emps = [Employee(employee_number=f"E{100 + i}", first_name=f, last_name=last, department_id=d.id,
                         position=pos, start_date=today - timedelta(days=400 - i * 50), email=f"e{i}@company.example",
                         national_id="000000018")
                for i, (f, last, d, pos) in enumerate([("דנה", "כהן", d1, "מנכ\"לית"), ("יוסי", "לוי", d2, "מפתח"),
                                                        ("נועה", "מזרחי", d2, "QA"), ("אבי", "פרץ", d3, "איש מכירות")])]
        db.add_all(emps)
        db.flush()
        assets = [
            Asset(asset_tag="LT-001", type=AssetType.laptop, brand="Dell", model="Latitude 7450", serial_number="DL7450A",
                  specs="i7 / 32GB / 1TB / Win11", purchase_date=today - timedelta(days=700),
                  purchase_price=Decimal("6200"), warranty_until=today + timedelta(days=20), supplier_id=s1.id),
            Asset(asset_tag="LT-002", type=AssetType.laptop, brand="Lenovo", model="ThinkPad T14", serial_number="LNT14B",
                  specs="Ryzen 7 / 16GB / 512GB", purchase_date=today - timedelta(days=200),
                  purchase_price=Decimal("5100"), warranty_until=today + timedelta(days=900), supplier_id=s1.id),
            Asset(asset_tag="MN-001", type=AssetType.monitor, brand="LG", model="27UP850", serial_number="LG27X"),
            Asset(asset_tag="PH-001", type=AssetType.phone, brand="Samsung", model="Galaxy S25", serial_number="SMS25"),
            Asset(asset_tag="LIC-001", type=AssetType.license, brand="Microsoft", model="Microsoft 365 Business",
                  license_key="XXXXX-DEMO-KEY", license_expiry=today + timedelta(days=12)),
        ]
        db.add_all(assets)
        db.flush()
        for a, e in [(assets[0], emps[1]), (assets[2], emps[1]), (assets[3], emps[3])]:
            a.employee_id, a.status = e.id, AssetStatus.assigned
            db.add(AssetAssignment(asset_id=a.id, employee_id=e.id, condition_out="תקין", acknowledged=True))
        for i, (cust, amount, days_ago, paid) in enumerate([
                (c1, "12000", 75, "14160"), (c2, "4200", 50, "2000"), (c1, "8000", 40, None), (c3, "2500", 20, "2950"),
                (c2, "15800", 10, None), (c1, "3100", 3, None)], 1):
            inv = Invoice(number=f"2026-{i:04d}", customer_id=cust.id, issue_date=today - timedelta(days=days_ago),
                          due_date=today - timedelta(days=days_ago) + timedelta(days=cust.payment_terms_days),
                          amount_before_vat=Decimal(amount), vat_rate=Decimal("18"),
                          allocation_number="123456789" if Decimal(amount) >= 5000 and i % 2 else None, payments=[])
            if paid:
                inv.payments.append(Payment(paid_on=inv.issue_date + timedelta(days=15), amount=Decimal(paid)))
            recompute(inv)
            db.add(inv)
        db.commit()
    print("Demo data created.")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    ca = sub.add_parser("create-admin")
    ca.add_argument("--email", required=True)
    ca.add_argument("--name", required=True)
    ca.add_argument("--password", help="omit to be prompted (recommended)")
    sub.add_parser("seed-demo")
    sub.add_parser("verify-audit")
    args = p.parse_args()
    Base.metadata.create_all(engine)
    if args.cmd == "create-admin":
        create_admin(args.email, args.name, args.password)
    elif args.cmd == "seed-demo":
        seed_demo()
    else:
        with SessionLocal() as db:
            print(audit.verify_chain(db))


if __name__ == "__main__":
    main()
