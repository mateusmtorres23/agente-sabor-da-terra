from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status

from ..dependencies import (
    get_current_user,
    get_triage_workflow_service,
    verify_triage_worker_auth,
)
from ..schemas.solicitation import SolicitationOut
from ..schemas.triage import (
    ReceivedEntryIngestRequest,
    ReceivedEntryIngestResponse,
    ReceivedEntryOut,
    TriageProcessRequest,
    TriageRecoveryResponse,
)
from ..services.triage import (
    ReceivedEntryInvalidStateError,
    ReceivedEntryNotFoundError,
    TriageWorkflowService,
)

router = APIRouter(prefix="/triage", tags=["triage"])

WorkflowService = Annotated[
    TriageWorkflowService,
    Depends(get_triage_workflow_service),
]


@router.post(
    "/entries",
    response_model=ReceivedEntryIngestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_triage_worker_auth)],
)
async def ingest_received_entry(
    payload: ReceivedEntryIngestRequest,
    service: WorkflowService,
) -> ReceivedEntryIngestResponse:
    entry, solicitation, enqueued = await service.ingest_entry(payload)
    return ReceivedEntryIngestResponse(
        entry=ReceivedEntryOut.model_validate(entry),
        solicitation=(
            SolicitationOut.model_validate(solicitation)
            if solicitation is not None
            else None
        ),
        enqueued=enqueued,
    )


@router.post(
    "/entries/{entry_id}/process",
    response_model=SolicitationOut | None,
    dependencies=[Depends(verify_triage_worker_auth)],
)
async def process_received_entry(
    entry_id: UUID,
    service: WorkflowService,
    payload: Annotated[TriageProcessRequest | None, Body()] = None,
) -> SolicitationOut | None:
    try:
        solicitation = await service.process_entry(
            entry_id,
            attempt_token=payload.attempt_token if payload else None,
        )
    except ReceivedEntryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    return (
        SolicitationOut.model_validate(solicitation)
        if solicitation is not None
        else None
    )


@router.post(
    "/entries/recover",
    response_model=TriageRecoveryResponse,
    dependencies=[Depends(verify_triage_worker_auth)],
)
async def recover_unenqueued_entries(
    service: WorkflowService,
) -> TriageRecoveryResponse:
    recovered = await service.recover_unenqueued_entries()
    return TriageRecoveryResponse(
        recovered_count=len(recovered),
        entry_ids=recovered,
    )


@router.get(
    "/entries/failed",
    response_model=list[ReceivedEntryOut],
    dependencies=[Depends(get_current_user)],
)
async def list_failed_entries(
    service: WorkflowService,
) -> list[ReceivedEntryOut]:
    entries = await service.list_failed_entries()
    return [ReceivedEntryOut.model_validate(entry) for entry in entries]


@router.post(
    "/entries/{entry_id}/retry",
    response_model=ReceivedEntryIngestResponse,
    dependencies=[Depends(get_current_user)],
)
async def retry_failed_entry(
    entry_id: UUID,
    service: WorkflowService,
) -> ReceivedEntryIngestResponse:
    try:
        entry, solicitation = await service.retry_failed_entry(entry_id)
    except ReceivedEntryNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except ReceivedEntryInvalidStateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return ReceivedEntryIngestResponse(
        entry=ReceivedEntryOut.model_validate(entry),
        solicitation=(
            SolicitationOut.model_validate(solicitation)
            if solicitation is not None
            else None
        ),
        enqueued=True,
    )