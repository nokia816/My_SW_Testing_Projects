from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import client_ip, require
from ..models import MovementType, Product, StockMovement, User, Warehouse
from ..schemas import MovementIn, MovementOut, ProductIn, ProductOut
from .crud import build_crud, get_or_404


def stock_of(db: Session, product_id: int, warehouse_id: int | None = None) -> int:
    stmt = select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(StockMovement.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
    return int(db.execute(stmt).scalar())


def product_out(db, p, user):
    out = ProductOut.model_validate(p)
    out.stock = stock_of(db, p.id)
    return out


products_router = build_crud(model=Product, resource="products", prefix="/api/products", schema_in=ProductIn,
                             schema_out=ProductOut, search=["sku", "name", "category", "barcode"], to_out=product_out,
                             filters={"category": "category", "supplier_id": "supplier_id"},
                             order_by=Product.name)

stock_router = APIRouter(prefix="/api/stock", tags=["stock"])


@stock_router.get("/levels")
def levels(product_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(require("stock"))):
    stmt = (select(StockMovement.product_id, StockMovement.warehouse_id, func.sum(StockMovement.quantity))
            .group_by(StockMovement.product_id, StockMovement.warehouse_id))
    if product_id:
        stmt = stmt.where(StockMovement.product_id == product_id)
    names = {w.id: w.name for w in db.execute(select(Warehouse)).scalars()}
    return [{"product_id": p, "warehouse_id": w, "warehouse": names.get(w), "quantity": int(q)}
            for p, w, q in db.execute(stmt)]


@stock_router.get("/movements")
def movements(product_id: int | None = None, warehouse_id: int | None = None, limit: int = Query(200, le=1000),
              offset: int = Query(0, ge=0), db: Session = Depends(get_db), _: User = Depends(require("stock"))):
    stmt = select(StockMovement)
    if product_id:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if warehouse_id:
        stmt = stmt.where(StockMovement.warehouse_id == warehouse_id)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
    rows = db.execute(stmt.order_by(StockMovement.id.desc()).limit(limit).offset(offset)).scalars()
    return {"total": total, "items": [MovementOut.model_validate(m) for m in rows]}


@stock_router.post("/movements", status_code=201)
def add_movement(data: MovementIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require("stock", "write"))):
    get_or_404(db, Product, data.product_id)
    get_or_404(db, Warehouse, data.warehouse_id)
    qty = data.quantity
    if data.type in (MovementType.receive, MovementType.return_):
        if qty <= 0:
            raise HTTPException(422, "כמות חייבת להיות חיובית")
    elif data.type in (MovementType.issue, MovementType.transfer):
        if qty <= 0:
            raise HTTPException(422, "כמות חייבת להיות חיובית")
        if stock_of(db, data.product_id, data.warehouse_id) < qty:
            raise HTTPException(409, "אין מספיק מלאי במחסן")
        qty = -qty
    elif qty == 0:
        raise HTTPException(422, "כמות התיקון לא יכולה להיות 0")
    common = dict(product_id=data.product_id, unit_cost=data.unit_cost, reference=data.reference, note=data.note,
                  user_id=user.id, type=data.type)
    rows = [StockMovement(warehouse_id=data.warehouse_id, quantity=qty, **common)]
    if data.type == MovementType.transfer:
        if not data.to_warehouse_id or data.to_warehouse_id == data.warehouse_id:
            raise HTTPException(422, "יש לבחור מחסן יעד שונה")
        get_or_404(db, Warehouse, data.to_warehouse_id)
        rows.append(StockMovement(warehouse_id=data.to_warehouse_id, quantity=-qty, **common))
    db.add_all(rows)
    db.commit()
    audit.record(db, user, "stock_" + data.type.value, "stock", rows[0].id, data.model_dump(), client_ip(request))
    return [MovementOut.model_validate(r) for r in rows]
