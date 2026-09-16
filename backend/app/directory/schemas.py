from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Organization provisioning ---
class ProvisionOrgRequest(BaseModel):
    """Create an organization together with its first admin user (platform.admin only)."""
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    timezone: str = "UTC"
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)
    admin_full_name: str


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    status: str


class ProvisionOrgResponse(BaseModel):
    organization: OrganizationOut
    admin_user_id: uuid.UUID


# --- Users ---
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role_keys: list[str] = Field(default_factory=list)
    scope_type: str = "organization"
    scope_id: uuid.UUID | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str
    status: str


# --- Departments ---
class DepartmentCreate(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None


# --- Teams ---
class TeamCreate(BaseModel):
    name: str
    department_id: uuid.UUID | None = None
    manager_user_id: uuid.UUID | None = None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    department_id: uuid.UUID | None
    manager_user_id: uuid.UUID | None


# --- Employees ---
class EmployeeCreate(BaseModel):
    full_name: str
    employee_code: str | None = None
    user_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    timezone: str | None = None
    hired_at: date | None = None
    hourly_rate: float | None = None  # requires rate.manage


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    department_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    timezone: str | None = None
    status: str | None = None
    hourly_rate: float | None = None  # requires rate.manage


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    full_name: str
    employee_code: str | None
    department_id: uuid.UUID | None
    team_id: uuid.UUID | None
    timezone: str | None
    status: str
    hired_at: date | None
    terminated_at: datetime | None
    # hourly_rate intentionally omitted here; exposed only via rate-gated field below
    hourly_rate: float | None = None
