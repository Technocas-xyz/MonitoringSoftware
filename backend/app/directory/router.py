"""Directory API: users, departments, teams, employees.

Every mutating endpoint is permission-gated and writes an audit record. Employee listing is
scope-narrowed: a caller without org-wide roles only sees employees in their scoped teams.
The `hourly_rate` field is only populated/accepted when the caller has rate permissions.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.core.security import hash_password
from app.directory.schemas import (
    DepartmentCreate,
    DepartmentOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    TeamCreate,
    TeamOut,
    UserCreate,
    UserOut,
)
from app.models.directory import Department, Employee, Team
from app.models.identity import Role, User, UserRole

router = APIRouter(tags=["directory"])


# ---------------------------------------------------------------- users
@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserCreate,
    principal: Principal = Depends(require_permission("user.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    dup = (
        await session.execute(
            select(User).where(
                User.organization_id == principal.organization_id, User.email == payload.email
            )
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="email already exists")

    user = User(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.flush()

    # Assign requested roles (only system roles or org roles that exist)
    for role_key in payload.role_keys:
        role = (
            await session.execute(
                select(Role).where(
                    Role.key == role_key,
                    (Role.organization_id == principal.organization_id)
                    | (Role.organization_id.is_(None)),
                )
            )
        ).scalars().first()
        if role:
            session.add(
                UserRole(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    role_id=role.id,
                    scope_type=payload.scope_type,
                    scope_id=payload.scope_id,
                )
            )

    await audit.record(
        session,
        action="user.create",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="user",
        target_id=user.id,
        new_value={"email": user.email, "roles": payload.role_keys},
    )
    await session.commit()
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    principal: Principal = Depends(require_permission("user.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(User))).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


# ---------------------------------------------------------------- departments
@router.post("/departments", response_model=DepartmentOut, status_code=201)
async def create_department(
    payload: DepartmentCreate,
    principal: Principal = Depends(require_permission("department.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    dept = Department(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        name=payload.name,
        parent_id=payload.parent_id,
    )
    session.add(dept)
    await audit.record(
        session,
        action="department.create",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="department",
        target_id=dept.id,
        new_value={"name": dept.name},
    )
    await session.commit()
    return DepartmentOut.model_validate(dept)


@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(Department))).scalars().all()
    return [DepartmentOut.model_validate(d) for d in rows]


# ---------------------------------------------------------------- teams
@router.post("/teams", response_model=TeamOut, status_code=201)
async def create_team(
    payload: TeamCreate,
    principal: Principal = Depends(require_permission("team.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    team = Team(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        name=payload.name,
        department_id=payload.department_id,
        manager_user_id=payload.manager_user_id,
    )
    session.add(team)
    await audit.record(
        session,
        action="team.create",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="team",
        target_id=team.id,
        new_value={"name": team.name},
    )
    await session.commit()
    return TeamOut.model_validate(team)


@router.get("/teams", response_model=list[TeamOut])
async def list_teams(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(Team))).scalars().all()
    return [TeamOut.model_validate(t) for t in rows]


# ---------------------------------------------------------------- employees
def _employee_out(emp: Employee, *, include_rate: bool) -> EmployeeOut:
    out = EmployeeOut.model_validate(emp)
    if not include_rate:
        out.hourly_rate = None
    return out


@router.post("/employees", response_model=EmployeeOut, status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    principal: Principal = Depends(require_permission("employee.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    can_rate = principal.has("rate.manage")
    if payload.hourly_rate is not None and not can_rate:
        raise HTTPException(status_code=403, detail="missing permission: rate.manage")

    emp = Employee(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        full_name=payload.full_name,
        employee_code=payload.employee_code,
        user_id=payload.user_id,
        department_id=payload.department_id,
        team_id=payload.team_id,
        timezone=payload.timezone,
        hired_at=payload.hired_at,
        hourly_rate=payload.hourly_rate if can_rate else None,
    )
    session.add(emp)
    await audit.record(
        session,
        action="employee.create",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="employee",
        target_id=emp.id,
        new_value={"full_name": emp.full_name, "code": emp.employee_code},
    )
    await session.commit()
    return _employee_out(emp, include_rate=principal.has("rate.view"))


@router.get("/employees", response_model=list[EmployeeOut])
async def list_employees(
    principal: Principal = Depends(require_permission("employee.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    stmt = select(Employee)
    # Scope narrowing: non org-wide callers only see their scoped teams (spec 90).
    if not principal.is_org_wide and principal.scoped_team_ids:
        stmt = stmt.where(Employee.team_id.in_(principal.scoped_team_ids))
    elif not principal.is_org_wide and not principal.scoped_team_ids:
        # employee role: can only see self
        stmt = stmt.where(Employee.user_id == principal.user_id)

    rows = (await session.execute(stmt)).scalars().all()
    include_rate = principal.has("rate.view")
    return [_employee_out(e, include_rate=include_rate) for e in rows]


@router.get("/employees/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: uuid.UUID,
    principal: Principal = Depends(require_permission("employee.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    emp = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="employee not found")
    return _employee_out(emp, include_rate=principal.has("rate.view"))


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    principal: Principal = Depends(require_permission("employee.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    emp = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="employee not found")

    changes = payload.model_dump(exclude_unset=True)
    if "hourly_rate" in changes and not principal.has("rate.manage"):
        raise HTTPException(status_code=403, detail="missing permission: rate.manage")

    old = {k: getattr(emp, k) for k in changes}
    for field, value in changes.items():
        setattr(emp, field, value)

    await audit.record(
        session,
        action="employee.update",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="employee",
        target_id=emp.id,
        old_value={k: str(v) for k, v in old.items()},
        new_value={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return _employee_out(emp, include_rate=principal.has("rate.view"))
