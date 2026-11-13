from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import client_ip, require
from ..models import (Asset, AssetAssignment, AssetStatus, Department, Employee, EmployeeStatus, Supplier, User,
                      Customer, Warehouse, utcnow)
from ..schemas import (AssetIn, AssetOut, AssignIn, AssignmentOut, CustomerIn, CustomerOut, DepartmentIn,
                       DepartmentOut, EmployeeIn, EmployeeOut, ReturnIn, SupplierIn, SupplierOut, WarehouseIn,
                       WarehouseOut)
from ..security import can
from .crud import build_crud, get_or_404

suppliers_router = build_crud(model=Supplier, resource="suppliers", prefix="/api/suppliers", schema_in=SupplierIn,
                              schema_out=SupplierOut, search=["name", "vat_id", "contact_name", "email"],
                              order_by=Supplier.name)
customers_router = build_crud(model=Customer, resource="customers", prefix="/api/customers", schema_in=CustomerIn,
                              schema_out=CustomerOut, search=["name", "vat_id", "contact_name", "email"],
                              order_by=Customer.name)
warehouses_router = build_crud(model=Warehouse, resource="warehouses", prefix="/api/warehouses",
                               schema_in=WarehouseIn, schema_out=WarehouseOut, search=["name", "location"],
                               order_by=Warehouse.name)
departments_router = build_crud(model=Department, resource="departments", prefix="/api/departments",
                                schema_in=DepartmentIn, schema_out=DepartmentOut, search=["name"],
                                order_by=Department.name)


# ---------------------------------------------------------------- employees
def employee_out(db: Session, e: Employee, user: User) -> EmployeeOut:
    out = EmployeeOut.model_validate(e)
    if not can(user.role, "employees_pii", "read"):
        out.national_id = None  # need-to-know: only HR/admin see ID numbers
    out.assets_count = db.execute(select(func.count()).where(Asset.employee_id == e.id)).scalar()
    return out


def employee_before_save(db: Session, obj, values: dict, user: User) -> dict:
    if "national_id" in values and not can(user.role, "employees_pii", "write"):
        values.pop("national_id")
    if values.get("department_id"):
        get_or_404(db, Department, values["department_id"])
    if values.get("status") == EmployeeStatus.left and obj is not None:
        held = db.execute(select(func.count()).where(Asset.employee_id == obj.id)).scalar()
        if held:
            raise HTTPException(409, f"לעובד עדיין {held} פריטי ציוד. יש להחזיר אותם לפני סיום העסקה")
    return values


def employee_before_delete(db: Session, obj: Employee) -> None:
    used = db.execute(select(func.count()).where(AssetAssignment.employee_id == obj.id)).scalar()
    if used:
        raise HTTPException(409, "לעובד יש היסטוריית ציוד. במקום למחוק, יש לסמן אותו כ'עזב'")


employees_router = build_crud(model=Employee, resource="employees", prefix="/api/employees", schema_in=EmployeeIn,
                              schema_out=EmployeeOut, search=["first_name", "last_name", "employee_number", "email",
                                                              "position"],
                              to_out=employee_out, before_save=employee_before_save,
                              before_delete=employee_before_delete,
                              filters={"status": "status", "department_id": "department_id"},
                              order_by=Employee.last_name)


@employees_router.post("/{emp_id}/offboard")
def start_offboarding(emp_id: int, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(require("employees", "write"))):
    emp = get_or_404(db, Employee, emp_id)
    emp.status = EmployeeStatus.offboarding
    db.commit()
    held = db.execute(select(Asset).where(Asset.employee_id == emp.id)).unique().scalars().all()
    audit.record(db, user, "offboard_start", "employees", emp.id, {"assets_to_return": [a.asset_tag for a in held]},
                 client_ip(request))
    return {"employee": employee_out(db, emp, user), "assets_to_return": [asset_out(db, a, user) for a in held]}


# ---------------------------------------------------------------- assets
def asset_out(db: Session, a: Asset, user: User) -> AssetOut:
    out = AssetOut.model_validate(a)
    out.has_license_key = bool(a.license_key)
    out.license_key = None  # revealed only through the explicit, audited /secret endpoint
    out.employee_name = f"{a.employee.first_name} {a.employee.last_name}" if a.employee else None
    return out


def asset_before_save(db: Session, obj, values: dict, user: User) -> dict:
    if "license_key" in values and not can(user.role, "asset_secrets", "write"):
        values.pop("license_key")
    if values.get("status") == AssetStatus.assigned:
        raise HTTPException(422, "שיוך לעובד מתבצע דרך פעולת 'מסירה לעובד'")
    if values.get("status") is None:
        values.pop("status", None)
        if obj is None:
            values["status"] = AssetStatus.in_stock
    elif obj is not None and obj.employee_id:
        raise HTTPException(409, "הפריט מוחזק ע\"י עובד. יש לבצע החזרה קודם")
    if values.get("supplier_id"):
        get_or_404(db, Supplier, values["supplier_id"])
    return values


assets_router = build_crud(model=Asset, resource="assets", prefix="/api/assets", schema_in=AssetIn,
                           schema_out=AssetOut, search=["asset_tag", "brand", "model", "serial_number", "specs"],
                           to_out=asset_out, before_save=asset_before_save,
                           filters={"status": "status", "type": "type", "employee_id": "employee_id"},
                           order_by=Asset.asset_tag)


def assignment_out(x: AssetAssignment) -> AssignmentOut:
    out = AssignmentOut.model_validate(x)
    out.asset_tag = x.asset.asset_tag
    out.employee_name = f"{x.employee.first_name} {x.employee.last_name}"
    return out


@assets_router.get("/{asset_id}/history")
def asset_history(asset_id: int, db: Session = Depends(get_db), _: User = Depends(require("assets"))):
    rows = db.execute(select(AssetAssignment).where(AssetAssignment.asset_id == asset_id)
                      .order_by(AssetAssignment.assigned_at.desc())).unique().scalars()
    return [assignment_out(x) for x in rows]


@assets_router.get("/{asset_id}/secret")
def asset_secret(asset_id: int, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require("asset_secrets"))):
    asset = get_or_404(db, Asset, asset_id)
    audit.record(db, user, "secret_view", "assets", asset.id, None, client_ip(request))
    return {"license_key": asset.license_key}


@assets_router.post("/{asset_id}/assign")
def assign_asset(asset_id: int, data: AssignIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require("assets", "write"))):
    asset = get_or_404(db, Asset, asset_id)
    emp = get_or_404(db, Employee, data.employee_id)
    if asset.employee_id:
        raise HTTPException(409, "הפריט כבר מוחזק ע\"י עובד")
    if asset.status in (AssetStatus.retired, AssetStatus.lost):
        raise HTTPException(409, "לא ניתן למסור פריט שנגרע/אבד")
    if emp.status != EmployeeStatus.active:
        raise HTTPException(409, "העובד אינו פעיל")
    asset.employee_id = emp.id
    asset.status = AssetStatus.assigned
    db.add(AssetAssignment(asset_id=asset.id, employee_id=emp.id, condition_out=data.condition, note=data.note,
                           acknowledged=data.acknowledged, by_user_id=user.id))
    db.commit()
    audit.record(db, user, "asset_assign", "assets", asset.id, {"employee_id": emp.id}, client_ip(request))
    db.refresh(asset)
    return asset_out(db, asset, user)


@assets_router.post("/{asset_id}/return")
def return_asset(asset_id: int, data: ReturnIn, request: Request, db: Session = Depends(get_db),
                 user: User = Depends(require("assets", "write"))):
    asset = get_or_404(db, Asset, asset_id)
    if not asset.employee_id:
        raise HTTPException(409, "הפריט אינו מוחזק ע\"י עובד")
    if data.new_status == AssetStatus.assigned:
        raise HTTPException(422, "סטטוס לא חוקי")
    open_row = db.execute(select(AssetAssignment).where(AssetAssignment.asset_id == asset.id,
                                                        AssetAssignment.returned_at.is_(None))).unique().scalar()
    if open_row:
        open_row.returned_at = utcnow()
        open_row.condition_in = data.condition
        if data.note:
            open_row.note = ((open_row.note or "") + " | " + data.note)[:300]
    prev = asset.employee_id
    asset.employee_id = None
    asset.status = data.new_status
    db.commit()
    audit.record(db, user, "asset_return", "assets", asset.id, {"employee_id": prev, "status": data.new_status},
                 client_ip(request))
    db.refresh(asset)
    return asset_out(db, asset, user)


@employees_router.get("/{emp_id}/assets")
def employee_assets(emp_id: int, db: Session = Depends(get_db), user: User = Depends(require("assets"))):
    current = db.execute(select(Asset).where(Asset.employee_id == emp_id)).unique().scalars()
    history = db.execute(select(AssetAssignment).where(AssetAssignment.employee_id == emp_id)
                         .order_by(AssetAssignment.assigned_at.desc())).unique().scalars()
    return {"current": [asset_out(db, a, user) for a in current], "history": [assignment_out(h) for h in history]}
