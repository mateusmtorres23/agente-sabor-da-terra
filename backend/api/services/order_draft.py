from decimal import Decimal
from typing import Any
from uuid import UUID

from ..models.order import Order
from ..models.order_draft import OrderDraft
from ..models.solicitation import SolicitationStatus
from ..repositories.chat import ChatRepository
from ..repositories.order_draft import OrderDraftRepository
from ..repositories.solicitation import SolicitationRepository
from ..schemas.order_draft import OrderDraftConfirmation, OrderDraftData
from .order import OrderService, OrderValidationError


class OrderDraftNotFoundError(LookupError):
    pass


class OrderDraftValidationError(ValueError):
    pass


class OrderDraftConflictError(ValueError):
    pass


class OrderDraftConversationFinishedError(ValueError):
    pass


class OrderDraftAlreadyConfirmedError(ValueError):
    def __init__(self, order_id: UUID) -> None:
        self.order_id = order_id
        super().__init__("Esta conversa já possui um pedido. Abra o pedido existente.")


class OrderDraftService:
    def __init__(
        self,
        repository: OrderDraftRepository,
        order_service: OrderService,
        chat_repository: ChatRepository,
        solicitation_repository: SolicitationRepository,
    ) -> None:
        self.repository = repository
        self.order_service = order_service
        self.chat_repository = chat_repository
        self.solicitation_repository = solicitation_repository
        self.session = repository.session

        repositories = (
            order_service.repository,
            order_service.product_repository,
            chat_repository,
            solicitation_repository,
        )
        if any(repo.session is not self.session for repo in repositories):
            raise ValueError("Os repositories precisam usar a mesma sessão do banco.")

    async def _get_session_id(
        self,
        user_id: UUID,
        *,
        session_id: UUID | None,
        solicitation_id: UUID | None,
        lock: bool,
        require_open: bool,
    ) -> UUID:
        if (session_id is None) == (solicitation_id is None):
            raise OrderDraftValidationError("Informe uma conversa ou uma solicitação.")

        if session_id is not None:
            chat = await self.chat_repository.get_session(
                session_id, user_id, lock=lock
            )
            if chat is None:
                raise OrderDraftNotFoundError("Conversa não encontrada.")
            return chat.id

        assert solicitation_id is not None
        solicitation = await self.solicitation_repository.get_by_id(
            solicitation_id, lock=lock
        )
        if solicitation is None:
            raise OrderDraftNotFoundError("Solicitação não encontrada.")
        if require_open and solicitation.status == SolicitationStatus.FINISHED:
            raise OrderDraftConversationFinishedError("A solicitação está finalizada.")


        chat = await self.solicitation_repository.get_session(
            solicitation.session_id, lock=lock
        )
        if chat is None or chat.user_id is not None:
            raise OrderDraftNotFoundError("Conversa da triagem não encontrada.")

        if require_open and solicitation.status == SolicitationStatus.RECEIVED:
            solicitation.status = SolicitationStatus.IN_REVIEW
        return chat.id

    async def create_draft(
        self,
        user_id: UUID,
        data: OrderDraftData,
        *,
        session_id: UUID | None = None,
        solicitation_id: UUID | None = None,
    ) -> OrderDraft:
        try:
            target = await self._get_session_id(
                user_id,
                session_id=session_id,
                solicitation_id=solicitation_id,
                lock=True,
                require_open=True,
            )
            existing = await self.order_service.repository.get_by_session(target)
            if existing is not None:
                raise OrderDraftAlreadyConfirmedError(existing.id)
            draft = OrderDraft(session_id=target, data=data.model_dump(mode="json"))
            self.repository.add(draft)
            await self.session.commit()
            return draft
        except Exception:
            await self.session.rollback()
            raise

    async def get_latest_draft(
        self,
        user_id: UUID,
        *,
        session_id: UUID | None = None,
        solicitation_id: UUID | None = None,
    ) -> OrderDraft | None:
        target = await self._get_session_id(
            user_id,
            session_id=session_id,
            solicitation_id=solicitation_id,
            lock=False,
            require_open=False,
        )
        return await self.repository.get_latest_for_session(target)

    async def get_linked_order(
        self,
        user_id: UUID,
        *,
        session_id: UUID | None = None,
        solicitation_id: UUID | None = None,
    ) -> Order | None:
        target = await self._get_session_id(
            user_id,
            session_id=session_id,
            solicitation_id=solicitation_id,
            lock=False,
            require_open=False,
        )
        return await self.order_service.repository.get_by_session(target)

    @staticmethod
    def _confirmation_snapshot(data: OrderDraftConfirmation) -> dict[str, Any]:
        snapshot = data.model_dump(mode="json")
        snapshot["items"].sort(key=lambda item: item["draft_item_id"])
        for item in snapshot["items"]:
            item["quantity"] = format(Decimal(item["quantity"]).normalize(), "f")
        return snapshot

    @staticmethod
    def _validate_selection(draft: OrderDraft, data: OrderDraftConfirmation) -> None:
        original = OrderDraftData.model_validate(draft.data)
        original_ids = {item.id for item in original.items}
        selected_ids = {item.draft_item_id for item in data.items}
        required_ids = {item.id for item in original.items if not item.conditional}
        if not selected_ids <= original_ids:
            raise OrderDraftValidationError(
                "Um dos itens não pertence a este rascunho."
            )
        if not required_ids <= selected_ids:
            raise OrderDraftValidationError(
                "Somente itens condicionais podem ser retirados da confirmação."
            )

    async def confirm(
        self,
        user_id: UUID,
        draft_id: UUID,
        data: OrderDraftConfirmation,
        *,
        session_id: UUID | None = None,
        solicitation_id: UUID | None = None,
    ) -> tuple[Order, bool]:
        try:
            target = await self._get_session_id(
                user_id,
                session_id=session_id,
                solicitation_id=solicitation_id,
                lock=True,
                require_open=True,
            )
            draft = await self.repository.get_by_id(
                draft_id, session_id=target, lock=True
            )
            if draft is None:
                raise OrderDraftNotFoundError("Rascunho não encontrado.")

            snapshot = self._confirmation_snapshot(data)
            existing = await self.order_service.repository.get_by_session(target)
            if existing is not None:
                if (
                    draft.confirmed_order_id == existing.id
                    and draft.confirmation_payload == snapshot
                ):
                    await self.session.commit()
                    return existing, False
                raise OrderDraftAlreadyConfirmedError(existing.id)

            if draft.confirmed_order_id is not None:
                raise OrderDraftValidationError(
                    "O vínculo do rascunho com o pedido está inconsistente."
                )
            if draft.version != data.draft_version:
                raise OrderDraftConflictError(
                    "O rascunho foi alterado. Recarregue antes de confirmar."
                )
            self._validate_selection(draft, data)

            order = await self.order_service.create_order(
                data.to_order_create(),
                session_id=target,
                commit=False,
            )
            draft.confirmed_order_id = order.id
            draft.confirmation_payload = snapshot
            await self.session.commit()
            return order, True
        except OrderValidationError as error:
            await self.session.rollback()
            raise OrderDraftValidationError(str(error)) from error
        except Exception:
            await self.session.rollback()
            raise
