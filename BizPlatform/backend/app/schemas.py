"""Strict input validation (whitelisted fields, length limits) and output shapes."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, create_model

from .models import AssetStatus, AssetType, EmployeeStatus, InvoiceStatus, MovementType, Role

Str = lambda n: Annotated[str, StringConstraints(strip_whitespace=True, max_length=n)]  # noqa: E731
Req = lambda n: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=n)]  # noqa: E731
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40, pattern=r"^[0-9+\-() ]*$")]
VatId = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20, pattern=r"^[0-9A-Za-z\-]*$")]
MoneyIn = Annotated[Decimal, Field(ge=0, le=Decimal("999999999999"), decimal_places=2)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def partial(model: type[BaseModel], name: str) -> type[BaseModel]:
    """Build an all-optional variant of a create schema for PATCH."""
    fields = {k: (Optional[v.annotation], None) for k, v in model.model_fields.items()}
    return create_model(name, __base__=In, **fields)


# ---------------------------------------------------------------- auth / users
class LoginIn(In):
    email: EmailStr
    password: Annotated[str, StringConstraints(max_length=128)]
    otp: Optional[Annotated[str, StringConstraints(max_length=10)]] = None


class UserOut(Out):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool
    totp_enabled: bool
    must_change_password: bool
    last_login_at: Optional[datetime]
    created_at: datetime


class UserCreate(In):
    email: EmailStr
    full_name: Req(200)
    role: Role = Role.viewer
    password: Annotated[str, StringConstraints(max_length=128)]


class UserUpdate(In):
    full_name: Optional[Req(200)] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    reset_password: Optional[Annotated[str, StringConstraints(max_length=128)]] = None
    reset_2fa: Optional[bool] = None


class ChangePasswordIn(In):
    current_password: Annotated[str, StringConstraints(max_length=128)]
    new_password: Annotated[str, StringConstraints(max_length=128)]


class OtpIn(In):
    code: Annotated[str, StringConstraints(max_length=10)]


# ---------------------------------------------------------------- partners
class SupplierIn(In):
    name: Req(200)
    vat_id: Optional[VatId] = None
    contact_name: Optional[Str(200)] = None
    phone: Optional[Phone] = None
    email: Optional[EmailStr] = None
    address: Optional[Str(300)] = None
    notes: Optional[Str(5000)] = None


class SupplierOut(Out):
    id: int
    name: str
    vat_id: Optional[str]
    contact_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    notes: Optional[str]


class CustomerIn(SupplierIn):
    payment_terms_days: Annotated[int, Field(ge=0, le=365)] = 30


class CustomerOut(SupplierOut):
    payment_terms_days: int


# ---------------------------------------------------------------- products / stock
class WarehouseIn(In):
    name: Req(120)
    location: Optional[Str(300)] = None


class WarehouseOut(Out):
    id: int
    name: str
    location: Optional[str]


class ProductIn(In):
    sku: Req(64)
    name: Req(200)
    description: Optional[Str(5000)] = None
    category: Optional[Str(100)] = None
    barcode: Optional[Str(64)] = None
    unit: Str(20) = "יח'"
    cost_price: MoneyIn = Decimal("0")
    sale_price: MoneyIn = Decimal("0")
    min_stock: Annotated[int, Field(ge=0, le=10_000_000)] = 0
    supplier_id: Optional[int] = None
    is_active: bool = True


class ProductOut(Out):
    id: int
    sku: str
    name: str
    description: Optional[str]
    category: Optional[str]
    barcode: Optional[str]
    unit: str
    cost_price: Decimal
    sale_price: Decimal
    min_stock: int
    supplier_id: Optional[int]
    is_active: bool
    stock: int = 0


class MovementIn(In):
    product_id: int
    warehouse_id: int
    type: MovementType
    quantity: Annotated[int, Field(ge=-10_000_000, le=10_000_000)]
    to_warehouse_id: Optional[int] = None  # for transfers
    unit_cost: Optional[MoneyIn] = None
    reference: Optional[Str(100)] = None
    note: Optional[Str(300)] = None


class MovementOut(Out):
    id: int
    ts: datetime
    product_id: int
    warehouse_id: int
    quantity: int
    type: MovementType
    unit_cost: Optional[Decimal]
    reference: Optional[str]
    note: Optional[str]
    user_id: Optional[int]


# ---------------------------------------------------------------- invoices (tracking)
class InvoiceIn(In):
    number: Req(50)
    doc_type: Annotated[str, StringConstraints(pattern=r"^(tax_invoice|tax_invoice_receipt|credit_note|proforma)$")] = "tax_invoice"
    allocation_number: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=20,
                                                                 pattern=r"^[0-9]*$")]] = None
    customer_id: int
    issue_date: date
    due_date: Optional[date] = None
    amount_before_vat: MoneyIn
    vat_rate: Optional[Annotated[Decimal, Field(ge=0, le=100)]] = None
    notes: Optional[Str(5000)] = None
    cancelled: bool = False


class PaymentIn(In):
    paid_on: date
    amount: Annotated[Decimal, Field(gt=0, le=Decimal("999999999999"), decimal_places=2)]
    method: Annotated[str, StringConstraints(pattern=r"^(bank_transfer|credit_card|check|cash|bit|other)$")] = "bank_transfer"
    reference: Optional[Str(100)] = None


class PaymentOut(Out):
    id: int
    invoice_id: int
    paid_on: date
    amount: Decimal
    method: str
    reference: Optional[str]


class InvoiceOut(Out):
    id: int
    number: str
    doc_type: str
    allocation_number: Optional[str]
    customer_id: int
    customer_name: Optional[str] = None
    issue_date: date
    due_date: date
    amount_before_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total: Decimal
    paid: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    status: InvoiceStatus
    overdue: bool = False
    allocation_required: bool = False
    notes: Optional[str]
    payments: list[PaymentOut] = []


# ---------------------------------------------------------------- people
class DepartmentIn(In):
    name: Req(120)
    manager_name: Optional[Str(200)] = None


class DepartmentOut(Out):
    id: int
    name: str
    manager_name: Optional[str]


class EmployeeIn(In):
    employee_number: Req(30)
    first_name: Req(100)
    last_name: Req(100)
    national_id: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=9,
                                                           pattern=r"^[0-9]*$")]] = None
    email: Optional[EmailStr] = None
    phone: Optional[Phone] = None
    department_id: Optional[int] = None
    position: Optional[Str(120)] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: EmployeeStatus = EmployeeStatus.active
    notes: Optional[Str(5000)] = None


class EmployeeOut(Out):
    id: int
    employee_number: str
    first_name: str
    last_name: str
    national_id: Optional[str] = None
    email: Optional[str]
    phone: Optional[str]
    department_id: Optional[int]
    position: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    status: EmployeeStatus
    notes: Optional[str]
    assets_count: int = 0


# ---------------------------------------------------------------- assets
class AssetIn(In):
    asset_tag: Req(50)
    type: AssetType
    brand: Optional[Str(100)] = None
    model: Optional[Str(150)] = None
    serial_number: Optional[Str(100)] = None
    specs: Optional[Str(300)] = None
    purchase_date: Optional[date] = None
    purchase_price: Optional[MoneyIn] = None
    supplier_id: Optional[int] = None
    warranty_until: Optional[date] = None
    license_key: Optional[Str(1000)] = None
    license_expiry: Optional[date] = None
    status: Optional[AssetStatus] = None  # assignment is done via /assign
    location: Optional[Str(150)] = None
    notes: Optional[Str(5000)] = None


class AssetOut(Out):
    id: int
    asset_tag: str
    type: AssetType
    brand: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    specs: Optional[str]
    purchase_date: Optional[date]
    purchase_price: Optional[Decimal]
    supplier_id: Optional[int]
    warranty_until: Optional[date]
    license_key: Optional[str] = None
    has_license_key: bool = False
    license_expiry: Optional[date]
    status: AssetStatus
    employee_id: Optional[int]
    employee_name: Optional[str] = None
    location: Optional[str]
    notes: Optional[str]


class AssignIn(In):
    employee_id: int
    condition: Optional[Str(200)] = None
    note: Optional[Str(300)] = None
    acknowledged: bool = False


class ReturnIn(In):
    condition: Optional[Str(200)] = None
    note: Optional[Str(300)] = None
    new_status: AssetStatus = AssetStatus.in_stock


class AssignmentOut(Out):
    id: int
    asset_id: int
    employee_id: int
    assigned_at: datetime
    returned_at: Optional[datetime]
    condition_out: Optional[str]
    condition_in: Optional[str]
    acknowledged: bool
    note: Optional[str]
    asset_tag: Optional[str] = None
    employee_name: Optional[str] = None


class AuditOut(Out):
    id: int
    ts: datetime
    user_email: Optional[str]
    action: str
    entity: str
    entity_id: Optional[str]
    details: Optional[dict]
    ip: Optional[str]
