"""Projects, tasks, and task time tracking (spec 34)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.core.time_authority import now, to_utc
from app.models.directory import Employee
from app.models.projects import Project, Task, TaskTimeEntry
from app.models.shifts import ACTIVE_STATES, Shift

router = APIRouter(tags=["projects"])


# ---- schemas ----
class ProjectCreate(BaseModel):
    name: str
    code: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    code: str | None
    status: str


class TaskCreate(BaseModel):
    project_id: uuid.UUID
    name: str


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: str


class TaskTimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    task_id: uuid.UUID
    employee_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int | None
    source: str


# ---- projects ----
@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate,
    principal: Principal = Depends(require_permission("project.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    p = Project(id=uuid.uuid4(), organization_id=principal.organization_id, name=payload.name, code=payload.code)
    session.add(p)
    await audit.record(
        session, action="project.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="project", target_id=p.id,
        new_value={"name": p.name},
    )
    await session.commit()
    return ProjectOut.model_validate(p)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    principal: Principal = Depends(require_permission("project.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(Project))).scalars().all()
    return [ProjectOut.model_validate(p) for p in rows]


# ---- tasks ----
@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    principal: Principal = Depends(require_permission("project.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    proj = (
        await session.execute(select(Project).where(Project.id == payload.project_id))
    ).scalar_one_or_none()
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    t = Task(id=uuid.uuid4(), organization_id=principal.organization_id, project_id=payload.project_id, name=payload.name)
    session.add(t)
    await audit.record(
        session, action="task.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="task", target_id=t.id,
        new_value={"name": t.name},
    )
    await session.commit()
    return TaskOut.model_validate(t)


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    project_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_permission("project.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    stmt = select(Task)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [TaskOut.model_validate(t) for t in rows]


# ---- task timer ----
async def _own_employee(session: AsyncSession, principal: Principal) -> Employee:
    emp = (
        await session.execute(select(Employee).where(Employee.user_id == principal.user_id))
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="no employee linked to this user")
    return emp


async def _current_shift_id(session, org_id, employee_id):
    shift = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id, Shift.employee_id == employee_id,
                Shift.state.in_(ACTIVE_STATES),
            )
        )
    ).scalars().first()
    return shift.id if shift else None


@router.post("/tasks/{task_id}/start", response_model=TaskTimeOut)
async def start_task(
    task_id: uuid.UUID,
    principal: Principal = Depends(require_permission("task.time_track")),
    session: AsyncSession = Depends(get_tenant_session),
):
    emp = await _own_employee(session, principal)
    task = (await session.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    # One open entry per employee: close any existing open entry first (switching tasks).
    open_entry = (
        await session.execute(
            select(TaskTimeEntry).where(
                TaskTimeEntry.organization_id == principal.organization_id,
                TaskTimeEntry.employee_id == emp.id,
                TaskTimeEntry.ended_at.is_(None),
            )
        )
    ).scalars().first()
    server_now = now()
    if open_entry:
        open_entry.ended_at = server_now
        open_entry.duration_seconds = int((server_now - to_utc(open_entry.started_at)).total_seconds())

    entry = TaskTimeEntry(
        id=uuid.uuid4(), organization_id=principal.organization_id, task_id=task_id,
        employee_id=emp.id, shift_id=await _current_shift_id(session, principal.organization_id, emp.id),
        started_at=server_now, source="agent",
    )
    session.add(entry)
    await audit.record(
        session, action="task.time.start", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="task_time_entry", target_id=entry.id,
        new_value={"task_id": str(task_id)},
    )
    await session.commit()
    return TaskTimeOut.model_validate(entry)


@router.post("/tasks/{task_id}/stop", response_model=TaskTimeOut)
async def stop_task(
    task_id: uuid.UUID,
    principal: Principal = Depends(require_permission("task.time_track")),
    session: AsyncSession = Depends(get_tenant_session),
):
    emp = await _own_employee(session, principal)
    entry = (
        await session.execute(
            select(TaskTimeEntry).where(
                TaskTimeEntry.organization_id == principal.organization_id,
                TaskTimeEntry.employee_id == emp.id,
                TaskTimeEntry.task_id == task_id,
                TaskTimeEntry.ended_at.is_(None),
            )
        )
    ).scalars().first()
    if entry is None:
        raise HTTPException(status_code=404, detail="no open time entry for this task")
    server_now = now()
    entry.ended_at = server_now
    entry.duration_seconds = int((server_now - to_utc(entry.started_at)).total_seconds())
    await audit.record(
        session, action="task.time.stop", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="task_time_entry", target_id=entry.id,
        new_value={"duration_seconds": entry.duration_seconds},
    )
    await session.commit()
    return TaskTimeOut.model_validate(entry)
