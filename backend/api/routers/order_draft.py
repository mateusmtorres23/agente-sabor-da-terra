from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..dependencies import get_current_user, get_order_draft_service
from ..models.user import User
from ..schemas.order import OrderResponse
from ..schemas.order_draft import OrderDraftConfirmation
from ..schemas.order_draft_response import (
    OrderDraftContextResponse,
    OrderDraftResponse,
)
from ..services.order_draft import (
    OrderDraftAlreadyConfirmedError,
    OrderDraftConflictError,
    OrderDraftConversationFinishedError,
    OrderDraftNotFoundError,
    OrderDraftService,
    OrderDraftValidationError,
)

router = APIRouter(tags=["order-drafts"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Service = Annotated[OrderDraftService, Depends(get_order_draft_service)]


@contextmanager
def _http_errors() -> Iterator[None]:
    try:
        yield
    except OrderDraftNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OrderDraftAlreadyConfirmedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "order_already_confirmed",
                "message": str(error),
                "order_id": str(error.order_id),
            },
        ) from error
    except OrderDraftConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "order_draft_version_conflict",
                "message": str(error),
            },
        ) from error
    except OrderDraftConversationFinishedError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "solicitation_finished",
                "message": str(error),
            },
        ) from error
    except OrderDraftValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def _context(
    user: User,
    service: OrderDraftService,
    **scope: UUID,
) -> OrderDraftContextResponse:
    with _http_errors():
        draft = await service.get_latest_draft(user.id, **scope)
        order = await service.get_linked_order(user.id, **scope)
        return OrderDraftContextResponse(
            draft=OrderDraftResponse.model_validate(draft) if draft else None,
            order=OrderResponse.model_validate(order) if order else None,
        )


async def _confirm(
    user: User,
    service: OrderDraftService,
    response: Response,
    draft_id: UUID,
    payload: OrderDraftConfirmation,
    **scope: UUID,
) -> OrderResponse:
    with _http_errors():
        order, created = await service.confirm(user.id, draft_id, payload, **scope)
        response.status_code = (
            status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
        return OrderResponse.model_validate(order)


@router.get(
    "/chat/sessions/{session_id}/order-draft",
    response_model=OrderDraftContextResponse,
)
async def get_private_order_draft(
    session_id: UUID,
    user: CurrentUser,
    service: Service,
) -> OrderDraftContextResponse:
    return await _context(user, service, session_id=session_id)


@router.post(
    "/chat/sessions/{session_id}/order-drafts/{draft_id}/confirm",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": OrderResponse}},
)
async def confirm_private_order_draft(
    session_id: UUID,
    draft_id: UUID,
    payload: OrderDraftConfirmation,
    user: CurrentUser,
    service: Service,
    response: Response,
) -> OrderResponse:
    return await _confirm(
        user, service, response, draft_id, payload, session_id=session_id
    )


@router.get(
    "/solicitations/{solicitation_id}/order-draft",
    response_model=OrderDraftContextResponse,
)
async def get_triage_order_draft(
    solicitation_id: UUID,
    user: CurrentUser,
    service: Service,
) -> OrderDraftContextResponse:
    return await _context(user, service, solicitation_id=solicitation_id)


@router.post(
    "/solicitations/{solicitation_id}/order-drafts/{draft_id}/confirm",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": OrderResponse}},
)
async def confirm_triage_order_draft(
    solicitation_id: UUID,
    draft_id: UUID,
    payload: OrderDraftConfirmation,
    user: CurrentUser,
    service: Service,
    response: Response,
) -> OrderResponse:
    return await _confirm(
        user, service, response, draft_id, payload, solicitation_id=solicitation_id
    )
