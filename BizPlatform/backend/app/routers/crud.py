"""Generic, permission-checked, audited CRUD router factory."""
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import client_ip, require
from ..models import User
from ..schemas import partial


def apply_search(stmt, model, fields: list[str], q: str | None):
    if q:
        like = f"%{q.strip()[:100]}%"
        stmt = stmt.where(or_(*[getattr(model, f).ilike(like) for f in fields]))
    return stmt


def commit_or_409(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "הרשומה מתנגשת ברשומה קיימת (ערך כפול) או מקושרת לרשומות אחרות") from exc


def get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, "לא נמצא")
    return obj


def build_crud(*, model, resource: str, prefix: str, schema_in, schema_out, search: list[str],
               to_out: Callable | None = None, before_save: Callable | None = None,
               order_by=None, filters: dict | None = None,
               before_delete: Callable | None = None) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[resource])
    schema_patch = partial(schema_in, f"{schema_in.__name__}Patch")
    to_out = to_out or (lambda db, o, u: schema_out.model_validate(o))
    filters = filters or {}

    @router.get("", response_model=dict)
    def list_items(request: Request, q: str | None = Query(None, max_length=100), limit: int = Query(100, ge=1, le=500),
                   offset: int = Query(0, ge=0), db: Session = Depends(get_db),
                   user: User = Depends(require(resource, "read"))):
        stmt = apply_search(select(model), model, search, q)
        for param, column in filters.items():
            val = request.query_params.get(param)
            if val not in (None, ""):
                stmt = stmt.where(getattr(model, column) == (int(val) if val.isdigit() else val))
        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar()
        stmt = stmt.order_by(order_by if order_by is not None else model.id.desc()).limit(limit).offset(offset)
        rows = db.execute(stmt).unique().scalars().all()
        return {"total": total, "items": [to_out(db, r, user) for r in rows]}

    @router.get("/{obj_id}")
    def get_item(obj_id: int, db: Session = Depends(get_db), user: User = Depends(require(resource, "read"))):
        return to_out(db, get_or_404(db, model, obj_id), user)

    @router.post("", status_code=201)
    def create_item(data: schema_in, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require(resource, "write"))):
        values = data.model_dump()
        if before_save:
            values = before_save(db, None, values, user)
        obj = model(**values)
        db.add(obj)
        commit_or_409(db)
        audit.record(db, user, "create", resource, obj.id, values, client_ip(request))
        return to_out(db, obj, user)

    @router.patch("/{obj_id}")
    def update_item(obj_id: int, data: schema_patch, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require(resource, "write"))):
        obj = get_or_404(db, model, obj_id)
        values = data.model_dump(exclude_unset=True)
        if before_save:
            values = before_save(db, obj, values, user)
        changes = {}
        for k, v in values.items():
            old = getattr(obj, k)
            if old != v:
                changes[k] = {"from": old, "to": v}
                setattr(obj, k, v)
        commit_or_409(db)
        if changes:
            audit.record(db, user, "update", resource, obj.id, changes, client_ip(request))
        return to_out(db, obj, user)

    @router.delete("/{obj_id}", status_code=204)
    def delete_item(obj_id: int, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require(resource, "write"))):
        obj = get_or_404(db, model, obj_id)
        if before_delete:
            before_delete(db, obj)
        snapshot = schema_out.model_validate(obj).model_dump() if hasattr(schema_out, "model_validate") else {}
        db.delete(obj)
        commit_or_409(db)
        audit.record(db, user, "delete", resource, obj_id, snapshot, client_ip(request))

    return router
