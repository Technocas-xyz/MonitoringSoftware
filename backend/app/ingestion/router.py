"""Event ingestion endpoint (device-authenticated, idempotent). Spec 52, doc 03 §8."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agent.deps import DevicePrincipal, get_device_principal
from app.core.tenant import open_tenant_session
from app.ingestion.service import ingest_batch

router = APIRouter(prefix="/ingest", tags=["ingestion"])


class IngestEventIn(BaseModel):
    event_id: str
    type: str
    timestamp: str | None = None
    payload: dict = Field(default_factory=dict)


class IngestBatchIn(BaseModel):
    device_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None
    sequence: int | None = None
    events: list[IngestEventIn]


class IngestResultOut(BaseModel):
    accepted: int
    duplicates: int
    rejected: int
    next_sequence_ack: int | None


@router.post("/events", response_model=IngestResultOut)
async def ingest_events(
    payload: IngestBatchIn,
    dp: DevicePrincipal = Depends(get_device_principal),
):
    async with open_tenant_session(str(dp.organization_id)) as session:
        result = await ingest_batch(
            session,
            organization_id=dp.organization_id,
            employee_id=dp.employee_id,
            device_id=dp.device_id,
            events=[e.model_dump() for e in payload.events],
            sequence=payload.sequence,
        )
        await session.commit()
    return IngestResultOut(
        accepted=result.accepted,
        duplicates=result.duplicates,
        rejected=result.rejected,
        next_sequence_ack=result.next_sequence_ack,
    )
