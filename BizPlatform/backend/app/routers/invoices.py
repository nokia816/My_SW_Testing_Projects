"""Invoice *tracking*: invoices are issued by the accounting dept; here we follow status, payments and debts."""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..deps import client_ip, require
from ..models import Customer, Invoice, InvoiceStatus, Payment, User
from ..schemas import InvoiceIn, InvoiceOut, PaymentIn, partial
from .crud import commit_or_409, get_or_404

router = APIRouter(prefix="/api/invoices", tags=["invoices"])
CENT = Decimal("0.01")
# Israeli "Invoices Israel" reform: allocation number required above this amount (before VAT), from 1.6.2026
ALLOCATION_THRESHOLD = Decimal("5000")
InvoicePatch = partial(InvoiceIn, "InvoicePatch")


def to_out(inv: Invoice) -> InvoiceOut:
    paid = sum((p.amount for p in inv.payments), Decimal("0"))
    out = InvoiceOut.model_validate(inv)
    out.customer_name = inv.customer.name if inv.customer else None
    out.paid = paid.quantize(CENT)
    out.balance = (inv.total - paid).quantize(CENT)
    out.overdue = inv.status in (InvoiceStatus.open, InvoiceStatus.partial) and inv.due_date < date.today()
    out.allocation_required = (inv.doc_type in ("tax_invoice", "tax_invoice_receipt")
                               and inv.amount_before_vat >= ALLOCATION_THRESHOLD and not inv.allocation_number)
    return out


def recompute(inv: Invoice) -> None:
    inv.vat_amount = (inv.amount_before_vat * inv.vat_rate / 100).quantize(CENT, ROUND_HALF_UP)
    inv.total = (inv.amount_before_vat + inv.vat_amount).quantize(CENT)
    if inv.status == InvoiceStatus.cancelled:
        return
    paid = sum((p.amount for p in inv.payments), Decimal("0"))
    inv.status = (InvoiceStatus.paid if paid >= inv.total and inv.total > 0
                  else InvoiceStatus.partial if paid > 0 else InvoiceStatus.open)


@router.get("")
def list_invoices(q: str | None = Query(None, max_length=100), status: InvoiceStatus | None = None,
                  customer_id: int | None = None, overdue: bool = False, date_from: date | None = None,
                  date_to: date | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db), _: User = Depends(require("invoices"))):
    stmt = select(Invoice).join(Customer)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Invoice.number.ilike(like), Customer.name.ilike(like),
                              Invoice.allocation_number.ilike(like)))
    if status:
        stmt = stmt.where(Invoice.status == status)
    if customer_id:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if overdue:
        stmt = stmt.where(Invoice.status.in_([InvoiceStatus.open, InvoiceStatus.partial]),
                          Invoice.due_date < date.today())
    if date_from:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.execute(stmt.order_by(Invoice.issue_date.desc(), Invoice.id.desc()).limit(limit).offset(offset))
    return {"total": total, "items": [to_out(i) for i in rows.unique().scalars()]}


@router.get("/{inv_id}")
def get_invoice(inv_id: int, db: Session = Depends(get_db), _: User = Depends(require("invoices"))):
    return to_out(get_or_404(db, Invoice, inv_id))


def _apply(db: Session, inv: Invoice, values: dict) -> None:
    cancelled = values.pop("cancelled", None)
    if "customer_id" in values:
        get_or_404(db, Customer, values["customer_id"])
    for k, v in values.items():
        setattr(inv, k, v)
    if inv.vat_rate is None:
        inv.vat_rate = Decimal(str(get_settings().vat_rate))
    if inv.due_date is None:
        cust = db.get(Customer, inv.customer_id)
        inv.due_date = inv.issue_date + timedelta(days=cust.payment_terms_days if cust else 30)
    if inv.due_date < inv.issue_date:
        raise HTTPException(422, "תאריך הפירעון לפני תאריך ההנפקה")
    if cancelled is True:
        inv.status = InvoiceStatus.cancelled
    elif cancelled is False and inv.status == InvoiceStatus.cancelled:
        inv.status = InvoiceStatus.open
    recompute(inv)


@router.post("", status_code=201)
def create_invoice(data: InvoiceIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require("invoices", "write"))):
    inv = Invoice(payments=[])
    values = data.model_dump()
    if values.get("vat_rate") is None:
        values.pop("vat_rate")
    _apply(db, inv, values)
    db.add(inv)
    commit_or_409(db)
    audit.record(db, user, "create", "invoices", inv.id, data.model_dump(), client_ip(request))
    return to_out(inv)


@router.patch("/{inv_id}")
def update_invoice(inv_id: int, data: InvoicePatch, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require("invoices", "write"))):
    inv = get_or_404(db, Invoice, inv_id)
    values = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None or k == "allocation_number"}
    _apply(db, inv, values)
    commit_or_409(db)
    audit.record(db, user, "update", "invoices", inv.id, data.model_dump(exclude_unset=True), client_ip(request))
    return to_out(inv)


@router.delete("/{inv_id}", status_code=204)
def delete_invoice(inv_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require("invoices", "write"))):
    inv = get_or_404(db, Invoice, inv_id)
    if inv.payments:
        raise HTTPException(409, "לא ניתן למחוק חשבונית עם תשלומים. יש לבטל אותה במקום")
    snap = to_out(inv).model_dump()
    db.delete(inv)
    db.commit()
    audit.record(db, user, "delete", "invoices", inv_id, snap, client_ip(request))


@router.post("/{inv_id}/payments", status_code=201)
def add_payment(inv_id: int, data: PaymentIn, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require("invoices", "write"))):
    inv = get_or_404(db, Invoice, inv_id)
    if inv.status == InvoiceStatus.cancelled:
        raise HTTPException(409, "החשבונית מבוטלת")
    balance = inv.total - sum((p.amount for p in inv.payments), Decimal("0"))
    if data.amount > balance:
        raise HTTPException(422, f"הסכום גבוה מהיתרה לתשלום ({balance})")
    inv.payments.append(Payment(**data.model_dump()))
    recompute(inv)
    db.commit()
    audit.record(db, user, "payment_add", "invoices", inv.id, data.model_dump(), client_ip(request))
    return to_out(inv)


@router.delete("/{inv_id}/payments/{payment_id}")
def delete_payment(inv_id: int, payment_id: int, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require("invoices", "write"))):
    inv = get_or_404(db, Invoice, inv_id)
    pay = next((p for p in inv.payments if p.id == payment_id), None)
    if pay is None:
        raise HTTPException(404, "לא נמצא")
    inv.payments.remove(pay)
    recompute(inv)
    db.commit()
    audit.record(db, user, "payment_delete", "invoices", inv.id, {"payment_id": payment_id, "amount": pay.amount},
                 client_ip(request))
    return to_out(inv)
