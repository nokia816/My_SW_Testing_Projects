import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import client_ip, current_user, require
from ..models import (Asset, AssetStatus, AuditLog, Customer, Employee, EmployeeStatus, Invoice, InvoiceStatus,
                      Payment, Product, StockMovement, Supplier, User)
from ..schemas import AuditOut
from ..security import can
from .invoices import to_out as invoice_out

router = APIRouter(prefix="/api", tags=["reports"])


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require("dashboard"))):
    today = date.today()
    out: dict = {}
    if can(user.role, "invoices", "read"):
        start = date(today.year - (1 if today.month < 12 else 0), (today.month % 12) + 1, 1)
        months = []
        d = start
        for _ in range(12):
            months.append(_month_key(d))
            d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        income = {m: Decimal("0") for m in months}
        for paid_on, amount in db.execute(select(Payment.paid_on, Payment.amount).where(Payment.paid_on >= start)):
            income[_month_key(paid_on)] = income.get(_month_key(paid_on), Decimal("0")) + amount
        invoiced = {m: Decimal("0") for m in months}
        for issued, total in db.execute(select(Invoice.issue_date, Invoice.total).where(
                Invoice.issue_date >= start, Invoice.status != InvoiceStatus.cancelled)):
            invoiced[_month_key(issued)] = invoiced.get(_month_key(issued), Decimal("0")) + total
        open_invs = [invoice_out(i) for i in db.execute(select(Invoice).where(
            Invoice.status.in_([InvoiceStatus.open, InvoiceStatus.partial]))).unique().scalars()]
        month_start = date(today.year, today.month, 1)
        out["finance"] = {
            "income_by_month": [{"month": m, "income": income[m], "invoiced": invoiced[m]} for m in months],
            "receivables": sum((i.balance for i in open_invs), Decimal("0")),
            "overdue_amount": sum((i.balance for i in open_invs if i.overdue), Decimal("0")),
            "overdue_count": sum(1 for i in open_invs if i.overdue),
            "income_this_month": income.get(_month_key(today), Decimal("0")),
            "income_ytd": db.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.paid_on >= date(today.year, 1, 1))).scalar(),
            "missing_allocation": sum(1 for i in open_invs if i.allocation_required),
            "top_overdue": sorted([i.model_dump(include={"id", "number", "customer_name", "balance", "due_date"})
                                   for i in open_invs if i.overdue], key=lambda x: x["due_date"])[:8],
            "month_start": month_start,
        }
    if can(user.role, "stock", "read"):
        stock = dict(db.execute(select(StockMovement.product_id, func.sum(StockMovement.quantity))
                                .group_by(StockMovement.product_id)).all())
        products = db.execute(select(Product).where(Product.is_active.is_(True))).scalars().all()
        low = [{"id": p.id, "sku": p.sku, "name": p.name, "stock": int(stock.get(p.id, 0)), "min_stock": p.min_stock}
               for p in products if int(stock.get(p.id, 0)) <= p.min_stock and p.min_stock > 0]
        out["inventory"] = {
            "products": len(products),
            "stock_value_cost": sum((p.cost_price * int(stock.get(p.id, 0)) for p in products), Decimal("0")),
            "stock_value_sale": sum((p.sale_price * int(stock.get(p.id, 0)) for p in products), Decimal("0")),
            "low_stock": sorted(low, key=lambda x: x["stock"] - x["min_stock"])[:10],
            "low_stock_count": len(low),
        }
    if can(user.role, "assets", "read"):
        by_status = dict(db.execute(select(Asset.status, func.count()).group_by(Asset.status)).all())
        by_type = dict(db.execute(select(Asset.type, func.count()).group_by(Asset.type)).all())
        soon = today + timedelta(days=30)
        warranty = db.execute(select(Asset).where(Asset.warranty_until.between(today, soon))
                              .order_by(Asset.warranty_until)).unique().scalars().all()
        licenses = db.execute(select(Asset).where(Asset.license_expiry <= soon,
                                                  Asset.status != AssetStatus.retired)
                              .order_by(Asset.license_expiry)).unique().scalars().all()
        offboarding = db.execute(select(Employee).where(Employee.status == EmployeeStatus.offboarding)).scalars().all()
        pending = []
        for e in offboarding:
            n = db.execute(select(func.count()).where(Asset.employee_id == e.id)).scalar()
            pending.append({"id": e.id, "name": f"{e.first_name} {e.last_name}", "assets_to_return": n})
        out["assets"] = {
            "by_status": {k.value: v for k, v in by_status.items()},
            "by_type": {k.value: v for k, v in by_type.items()},
            "total": sum(by_status.values()),
            "warranty_expiring": [{"id": a.id, "asset_tag": a.asset_tag, "model": a.model,
                                   "date": a.warranty_until} for a in warranty],
            "licenses_expiring": [{"id": a.id, "asset_tag": a.asset_tag, "model": a.model,
                                   "date": a.license_expiry, "expired": a.license_expiry < today} for a in licenses],
            "offboarding": pending,
        }
    if can(user.role, "employees", "read"):
        by = dict(db.execute(select(Employee.status, func.count()).group_by(Employee.status)).all())
        out["people"] = {k.value: v for k, v in by.items()}
    return out


@router.get("/audit")
def audit_list(entity: str | None = None, action: str | None = None, limit: int = Query(200, le=1000),
               offset: int = Query(0, ge=0), db: Session = Depends(get_db), _: User = Depends(require("audit"))):
    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).scalars()
    return {"total": total, "items": [AuditOut.model_validate(r) for r in rows]}


@router.get("/audit/verify")
def audit_verify(db: Session = Depends(get_db), _: User = Depends(require("audit"))):
    return audit.verify_chain(db)


# ---------------------------------------------------------------- CSV export (Excel-compatible, UTF-8 BOM)
def _safe(v) -> str:
    """Neutralise CSV/formula injection (=, +, -, @ at cell start)."""
    s = "" if v is None else (v.value if hasattr(v, "value") else str(v))
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


EXPORTS = {
    "products": ("products", Product, ["sku", "name", "category", "barcode", "unit", "cost_price", "sale_price",
                                       "min_stock", "is_active"]),
    "customers": ("customers", Customer, ["name", "vat_id", "contact_name", "phone", "email", "address",
                                          "payment_terms_days"]),
    "suppliers": ("suppliers", Supplier, ["name", "vat_id", "contact_name", "phone", "email", "address"]),
    "employees": ("employees", Employee, ["employee_number", "first_name", "last_name", "email", "phone",
                                          "position", "start_date", "end_date", "status"]),
    "assets": ("assets", Asset, ["asset_tag", "type", "brand", "model", "serial_number", "specs", "purchase_date",
                                 "purchase_price", "warranty_until", "license_expiry", "status", "location"]),
    "invoices": ("invoices", Invoice, ["number", "doc_type", "allocation_number", "issue_date", "due_date",
                                       "amount_before_vat", "vat_amount", "total", "status"]),
}


@router.get("/export/{name}")
def export_csv(name: str, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if name not in EXPORTS:
        raise HTTPException(404, "לא נמצא")
    resource, model, cols = EXPORTS[name]
    if not can(user.role, resource, "read"):
        raise HTTPException(403, "אין הרשאה לפעולה זו")
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    extra = ["customer"] if model is Invoice else (["holder"] if model is Asset else [])
    w.writerow(cols + extra)
    for row in db.execute(select(model).order_by(model.id)).unique().scalars():
        vals = [_safe(getattr(row, c)) for c in cols]
        if model is Invoice:
            vals.append(_safe(row.customer.name))
        elif model is Asset:
            vals.append(_safe(f"{row.employee.first_name} {row.employee.last_name}" if row.employee else ""))
        w.writerow(vals)
    audit.record(db, user, "export", resource, None, {"rows": "all"}, client_ip(request))
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}-{date.today()}.csv"'})
