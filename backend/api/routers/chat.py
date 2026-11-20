from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_chat_service, get_current_user, get_lot_draft_service
from ..models.user import User
from ..schemas.chat import MessageCreate, MessageOut, SessionDetail, SessionOut
from ..schemas.lot_draft import (
    LotDraftAvailabilityUpdate,
    LotDraftCreate,
    LotDraftOut,
    LotDraftUpdate,
)
from ..services.chat import ChatService, SessionNotFoundError
from ..services.lot import LotConflictError, LotNotFoundError, LotValidationError
from ..services.lot_draft import (
    LotDraftNotFoundError,
    LotDraftService,
    LotDraftValidationError,
)

router = APIRouter(prefix="/chat", tags=["chat"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[ChatService, Depends(get_chat_service)]

def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Session not found."
    )

@router.post(
    "/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED
)
async def create_session(user: CurrentUser, service: Service) -> SessionOut:
    chat = await service.create_session(user.id)
    return SessionOut.model_validate(chat)

@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: CurrentUser, service: Service) -> list[SessionOut]:
    sessions = await service.list_session(user.id)
    return [SessionOut.model_validate(s) for s in sessions]

@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: UUID,
    user: CurrentUser,
    service: Service,
) -> SessionDetail:
    try:
        chat, messages = await service.get_session_with_messages(
            session_id, user.id
        )
    except SessionNotFoundError as error:
        raise _not_found() from error

    return SessionDetail(
        **SessionOut.model_validate(chat).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages]
    )

@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    session_id: UUID,
    payload: MessageCreate,
    user: CurrentUser,
    service: Service
) -> MessageOut:
    try: 
        message = await service.add_message(session_id, user.id, payload.content)
    except SessionNotFoundError as error:
        raise _not_found() from error

    return MessageOut.model_validate(message)


DraftService = Annotated[LotDraftService, Depends(get_lot_draft_service)]


def _map_draft_error(error: Exception) -> HTTPException:
    if isinstance(error, (LotDraftNotFoundError, LotNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, (LotDraftValidationError, LotValidationError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        )
    if isinstance(error, LotConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    raise error


@router.post(
    "/sessions/{session_id}/lot-drafts",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_lot_draft(
    session_id: UUID,
    payload: LotDraftCreate,
    user: CurrentUser,
    draft_service: DraftService,
) -> MessageOut:
    try:
        message, _ = await draft_service.create_draft_message(session_id, user, payload)
    except Exception as error:
        raise _map_draft_error(error)
    return MessageOut.model_validate(message)


@router.patch(
    "/lot-drafts/{draft_id}",
    response_model=LotDraftOut,
)
async def update_lot_draft(
    draft_id: UUID,
    payload: LotDraftUpdate,
    user: CurrentUser,
    draft_service: DraftService,
) -> LotDraftOut:
    try:
        draft = await draft_service.update_draft(draft_id, user, payload)
    except Exception as error:
        raise _map_draft_error(error)
    return LotDraftService.to_out(draft)


@router.post(
    "/lot-drafts/{draft_id}/availability",
    response_model=LotDraftOut,
)
async def set_lot_draft_availability(
    draft_id: UUID,
    payload: LotDraftAvailabilityUpdate,
    user: CurrentUser,
    draft_service: DraftService,
) -> LotDraftOut:
    try:
        draft = await draft_service.set_availability(draft_id, user, payload)
    except Exception as error:
        raise _map_draft_error(error)
    return LotDraftService.to_out(draft)


@router.post(
    "/lot-drafts/{draft_id}/confirm",
    response_model=LotDraftOut,
)
async def confirm_lot_draft(
    draft_id: UUID,
    user: CurrentUser,
    draft_service: DraftService,
) -> LotDraftOut:
    try:
        draft = await draft_service.confirm_draft(draft_id, user)
    except Exception as error:
        raise _map_draft_error(error)
    return LotDraftService.to_out(draft)