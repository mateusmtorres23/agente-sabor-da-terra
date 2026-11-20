from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.helpers.triage import build_triage_session_title
from api.models.chat_message import ChatMessage
from api.models.chat_session import ChatSession
from api.models.solicitation import Solicitation
from api.repositories.solicitation import SolicitationRepository
from api.schemas.solicitation import SolicitationCreate
from api.services.solicitation import SolicitationService


def _payload() -> dict[str, Any]:
    return {
        "input": {
            "message_text": "Preciso de 10 kg de tomate até amanhã.",
            "received_at": "2026-10-30",
            "source_id": "PED-ROLLBACK",
        },
        "analysis": {
            "summary": "Pedido de tomate para o dia seguinte.",
            "request_type": "pedido",
            "urgency": "indeterminada",
            "urgency_reason": "A classificar.",
            "received_date_reference": "2026-10-30",
            "extracted_data": {
                "delivery_date_start": "2026-10-31",
            },
        },
    }


@pytest.mark.parametrize(
    "failure_point",
    [
        "session",
        "original_message",
        "analysis_message",
        "solicitation",
    ],
)
@pytest.mark.asyncio
async def test_create_rolls_back_every_record_when_a_write_fails(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    repository = SolicitationRepository(db_session)
    service = SolicitationService(repository)
    original_create_session = SolicitationRepository.create_session
    original_add_message = SolicitationRepository.add_message
    original_add = SolicitationRepository.add

    payload_obj = SolicitationCreate.model_validate(_payload())
    expected_title = build_triage_session_title(
        payload_obj.input, payload_obj.analysis
    )
    solicitation_id = uuid4()

    async def fail_after_session(
        self: SolicitationRepository,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        await original_create_session(self, *args, **kwargs)
        raise RuntimeError("falha simulada")

    message_calls = 0

    async def fail_after_message(
        self: SolicitationRepository,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        nonlocal message_calls
        message_calls += 1
        message = await original_add_message(self, *args, **kwargs)
        should_fail = (
            failure_point == "original_message" and message_calls == 1
        ) or (
            failure_point == "analysis_message" and message_calls == 2
        )
        if should_fail:
            raise RuntimeError("falha simulada")
        return message

    def fail_after_solicitation(
        self: SolicitationRepository,
        solicitation: Solicitation,
    ) -> None:
        original_add(self, solicitation)
        raise RuntimeError("falha simulada")

    if failure_point == "session":
        monkeypatch.setattr(
            SolicitationRepository,
            "create_session",
            fail_after_session,
        )
    elif failure_point in {"original_message", "analysis_message"}:
        monkeypatch.setattr(
            SolicitationRepository,
            "add_message",
            fail_after_message,
        )
    else:
        monkeypatch.setattr(
            SolicitationRepository,
            "add",
            fail_after_solicitation,
        )

    with pytest.raises(RuntimeError, match="falha simulada"):
        await service.create_from_analysis(
            payload_obj,
            solicitation_id=solicitation_id,
        )

    rolled_back_sessions = await db_session.scalar(
        select(func.count())
        .select_from(ChatSession)
        .where(ChatSession.title == expected_title)
    )
    assert rolled_back_sessions == 0
    rolled_back_messages = await db_session.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.title == expected_title)
    )
    assert rolled_back_messages == 0
    assert (
        await db_session.get(Solicitation, solicitation_id)
    ) is None
