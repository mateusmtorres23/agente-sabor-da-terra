from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.triage.agent import analyze_triage_message
from ..agents.triage.schemas import TriageAnalysis, TriageInput
from ..models.received_entry import ReceivedEntry, ReceivedEntryStatus
from ..models.solicitation import Solicitation
from ..repositories.received_entry import ReceivedEntryRepository
from ..repositories.solicitation import SolicitationRepository
from ..schemas.solicitation import SolicitationCreate
from ..schemas.triage import ReceivedEntryIngestRequest
from ..tasks.triage_queue import TriageTaskQueue
from .solicitation import SolicitationService

RECEIVED_ENTRY_NAMESPACE = uuid5(
    NAMESPACE_URL,
    "https://sabordaterra.coop.br/received-entries",
)

TriageAnalyzer = Callable[[TriageInput], Awaitable[TriageAnalysis]]


class ReceivedEntryNotFoundError(LookupError):
    pass


class ReceivedEntryInvalidStateError(ValueError):
    pass


def compute_received_entry_id(
    *,
    source_channel: str,
    external_id: str | None = None,
    source_context: str | None = None,
    explicit_id: UUID | None = None,
) -> UUID:
    if explicit_id is not None:
        return explicit_id
    if external_id and external_id.strip():
        channel = source_channel.strip().lower()
        context = (source_context or "").strip().lower()
        ext = external_id.strip()
        return uuid5(RECEIVED_ENTRY_NAMESPACE, f"{channel}:{context}:{ext}")
    return uuid4()


class TriageWorkflowService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        task_queue: TriageTaskQueue | None = None,
        analyzer: TriageAnalyzer = analyze_triage_message,
    ) -> None:
        self.session = session
        self.entry_repo = ReceivedEntryRepository(session)
        self.solicitation_repo = SolicitationRepository(session)
        self.solicitation_service = SolicitationService(self.solicitation_repo)
        self.task_queue = task_queue
        self.analyzer = analyzer

    async def ingest_entry(
        self,
        payload: ReceivedEntryIngestRequest,
    ) -> tuple[ReceivedEntry, Solicitation | None, bool]:
        entry_id = compute_received_entry_id(
            source_channel=payload.source_channel,
            external_id=payload.external_id,
            source_context=payload.source_context,
            explicit_id=payload.id,
        )

        entry = await self.entry_repo.get_by_id(entry_id, lock=True)
        if entry is None:
            received_at = payload.received_at or datetime.now(UTC)
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=UTC)

            entry = ReceivedEntry(
                id=entry_id,
                original_text=payload.message_text.strip(),
                sender=payload.sender.strip(),
                source_channel=payload.source_channel.strip(),
                source_context=(
                    payload.source_context.strip()
                    if payload.source_context
                    else None
                ),
                external_id=(
                    payload.external_id.strip()
                    if payload.external_id
                    else None
                ),
                received_at=received_at,
                triage_status=ReceivedEntryStatus.PENDING,
            )
            self.entry_repo.add(entry)
            try:
                await self.session.commit()
            except IntegrityError:
                await self.session.rollback()
                entry = await self.entry_repo.get_by_id(entry_id, lock=True)
                if entry is None:
                    raise

        if entry.triage_status == ReceivedEntryStatus.COMPLETED:
            solicitation = await self.solicitation_repo.get_by_id(entry.id)
            return entry, solicitation, False

        if not payload.enqueue:
            return entry, None, False

        if entry.triage_status == ReceivedEntryStatus.PROCESSING:
            return entry, None, False

        enqueued = await self._enqueue_or_run_inline(entry.id)
        refreshed = await self.entry_repo.get_by_id(entry.id)
        solicitation = (
            await self.solicitation_repo.get_by_id(entry.id)
            if refreshed and refreshed.triage_status == ReceivedEntryStatus.COMPLETED
            else None
        )
        return refreshed or entry, solicitation, enqueued

    async def retry_failed_entry(
        self,
        entry_id: UUID,
    ) -> tuple[ReceivedEntry, Solicitation | None]:
        entry = await self.entry_repo.get_by_id(entry_id, lock=True)
        if entry is None:
            raise ReceivedEntryNotFoundError("Entrada recebida não encontrada.")

        if entry.triage_status == ReceivedEntryStatus.COMPLETED:
            await self.session.commit()
            solicitation = await self.solicitation_repo.get_by_id(entry.id)
            return entry, solicitation

        if entry.triage_status == ReceivedEntryStatus.PROCESSING:
            # Outra requisição simultânea já iniciou a tentativa vigente.
            await self.session.commit()
            return entry, None

        if entry.triage_status != ReceivedEntryStatus.FAILED:
            await self.session.commit()
            raise ReceivedEntryInvalidStateError(
                "Apenas entradas com falha podem ser reprocessadas manualmente."
            )

        attempt_token = uuid4()
        entry.triage_status = ReceivedEntryStatus.PROCESSING
        entry.attempt_token = attempt_token
        entry.failure_reason = None
        entry.enqueued_at = None
        entry.updated_at = datetime.now(UTC)
        await self.session.commit()

        await self._enqueue_or_run_inline(
            entry.id,
            attempt_token=attempt_token,
            already_claimed=True,
        )

        refreshed = await self.entry_repo.get_by_id(entry.id)
        solicitation = (
            await self.solicitation_repo.get_by_id(entry.id)
            if refreshed and refreshed.triage_status == ReceivedEntryStatus.COMPLETED
            else None
        )
        return refreshed or entry, solicitation

    async def process_entry(
        self,
        entry_id: UUID,
        *,
        attempt_token: UUID | None = None,
        already_claimed: bool = False,
    ) -> Solicitation | None:
        entry = await self.entry_repo.get_by_id(entry_id, lock=True)
        if entry is None:
            raise ReceivedEntryNotFoundError("Entrada recebida não encontrada.")

        if entry.triage_status == ReceivedEntryStatus.COMPLETED:
            await self.session.commit()
            return await self.solicitation_repo.get_by_id(entry.id)

        if already_claimed:
            if (
                entry.triage_status != ReceivedEntryStatus.PROCESSING
                or entry.attempt_token != attempt_token
            ):
                await self.session.commit()
                return None
            active_token = attempt_token
        else:
            if (
                attempt_token is not None
                and entry.attempt_token is not None
                and entry.attempt_token != attempt_token
            ):
                await self.session.commit()
                return None

            if (
                entry.triage_status == ReceivedEntryStatus.PROCESSING
                and attempt_token is None
            ):
                await self.session.commit()
                return None

            active_token = attempt_token or uuid4()
            entry.triage_status = ReceivedEntryStatus.PROCESSING
            entry.attempt_token = active_token
            entry.failure_reason = None
            entry.updated_at = datetime.now(UTC)
            await self.session.commit()

        triage_input = TriageInput(
            message_text=entry.original_text,
            received_at=entry.received_at,
            sender=entry.sender,
            channel=entry.source_channel,
            source_id=entry.external_id or str(entry.id),
        )

        try:
            analysis = await self.analyzer(triage_input)
        except Exception as exc:  # noqa: BLE001
            await self._mark_attempt_failed(entry_id, active_token, str(exc))
            return None

        # Reabre bloqueio para gravar solicitação + sessão + mensagens + conclusão
        # na mesma transação atômica, validando se active_token ainda é o vigente.
        try:
            locked_entry = await self.entry_repo.get_by_id(entry_id, lock=True)
            if locked_entry is None:
                await self.session.rollback()
                return None

            if locked_entry.triage_status == ReceivedEntryStatus.COMPLETED:
                await self.session.commit()
                return await self.solicitation_repo.get_by_id(entry_id)

            if (
                locked_entry.triage_status != ReceivedEntryStatus.PROCESSING
                or locked_entry.attempt_token != active_token
            ):
                # Resultado atrasado de tentativa anterior: descarta sem sobrescrever.
                await self.session.rollback()
                return None

            solicitation = await self.solicitation_service.persist_from_analysis(
                SolicitationCreate(
                    id=locked_entry.id,
                    input=triage_input,
                    analysis=analysis,
                ),
                solicitation_id=locked_entry.id,
            )
            locked_entry.triage_status = ReceivedEntryStatus.COMPLETED
            locked_entry.failure_reason = None
            locked_entry.updated_at = datetime.now(UTC)

            await self.session.commit()
            return solicitation
        except Exception as exc:  # noqa: BLE001
            await self.session.rollback()
            await self._mark_attempt_failed(entry_id, active_token, str(exc))
            raise

    async def recover_unenqueued_entries(
        self,
        *,
        pending_grace_seconds: int = 30,
        processing_timeout_seconds: int = 600,
    ) -> list[UUID]:
        now = datetime.now(UTC)
        candidates = await self.entry_repo.list_recoverable_for_scheduler(
            pending_before=now - timedelta(seconds=pending_grace_seconds),
            processing_before=now - timedelta(seconds=processing_timeout_seconds),
        )
        recovered_ids: list[UUID] = []
        for candidate in candidates:
            locked = await self.entry_repo.get_by_id(candidate.id, lock=True)
            if locked is None or locked.triage_status == ReceivedEntryStatus.COMPLETED:
                await self.session.commit()
                continue

            if locked.triage_status == ReceivedEntryStatus.PROCESSING:
                locked.triage_status = ReceivedEntryStatus.PENDING
                locked.attempt_token = None
                locked.enqueued_at = None
                locked.updated_at = now
                await self.session.commit()

            enqueued = await self._enqueue_or_run_inline(locked.id)
            if enqueued:
                recovered_ids.append(locked.id)

        return recovered_ids

    async def list_failed_entries(self) -> list[ReceivedEntry]:
        return await self.entry_repo.list_failed_and_retrying()

    async def _enqueue_or_run_inline(
        self,
        entry_id: UUID,
        *,
        attempt_token: UUID | None = None,
        already_claimed: bool = False,
    ) -> bool:
        if self.task_queue is None:
            await self.process_entry(
                entry_id,
                attempt_token=attempt_token,
                already_claimed=already_claimed,
            )
            return True

        try:
            await self.task_queue.enqueue_triage(
                entry_id,
                attempt_token=attempt_token,
            )
        except Exception:  # noqa: BLE001
            # Mantém a entrada persistida sem enqueued_at para recuperação pelo Scheduler
            # (ou como FAILED caso tenha sido uma retentativa manual).
            locked = await self.entry_repo.get_by_id(entry_id, lock=True)
            if locked is not None and locked.triage_status != ReceivedEntryStatus.COMPLETED:
                if already_claimed and locked.attempt_token == attempt_token:
                    locked.triage_status = ReceivedEntryStatus.FAILED
                    locked.failure_reason = "Falha ao enfileirar nova tentativa."
                    locked.updated_at = datetime.now(UTC)
                await self.session.commit()
            return False

        locked = await self.entry_repo.get_by_id(entry_id, lock=True)
        if locked is not None:
            locked.enqueued_at = datetime.now(UTC)
            await self.session.commit()
        return True

    async def _mark_attempt_failed(
        self,
        entry_id: UUID,
        attempt_token: UUID,
        reason: str,
    ) -> None:
        locked = await self.entry_repo.get_by_id(entry_id, lock=True)
        if (
            locked is not None
            and locked.triage_status == ReceivedEntryStatus.PROCESSING
            and locked.attempt_token == attempt_token
        ):
            locked.triage_status = ReceivedEntryStatus.FAILED
            locked.failure_reason = reason[:500]
            locked.updated_at = datetime.now(UTC)
            await self.session.commit()
        else:
            await self.session.rollback()