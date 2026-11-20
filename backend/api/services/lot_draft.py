from uuid import UUID

from ..models.chat_message import ChatMessage, ChatMessageRole
from ..models.chat_session import ChatSession
from ..models.lot_draft import LotDraft
from ..models.user import User
from ..repositories.chat import ChatRepository
from ..repositories.lot_draft import LotDraftRepository
from ..repositories.order import OrderRepository
from ..schemas.lot import LotCreate
from ..schemas.lot_draft import (
    LotDraftAvailabilityUpdate,
    LotDraftConfirmRequest,
    LotDraftCreate,
    LotDraftOut,
    LotDraftUpdate,
    build_lot_draft_out,
)
from .lot import LotConflictError, LotNotFoundError, LotService, LotValidationError


class LotDraftNotFoundError(LookupError):
    pass


class LotDraftValidationError(ValueError):
    pass


class LotDraftConflictError(RuntimeError):
    pass


class LotDraftService:
    def __init__(
        self,
        draft_repository: LotDraftRepository,
        chat_repository: ChatRepository,
        order_repository: OrderRepository,
        lot_service: LotService,
    ) -> None:
        self.draft_repository = draft_repository
        self.chat_repository = chat_repository
        self.order_repository = order_repository
        self.lot_service = lot_service

    async def create_draft_message(
        self,
        session_id: UUID,
        user: User,
        payload: LotDraftCreate,
    ) -> tuple[ChatMessage, LotDraft]:
        session = await self._get_authorized_session(session_id, user)

        if payload.order_id is not None:
            order = await self.order_repository.get_by_id(payload.order_id, lock=False)
            if order is None:
                raise LotDraftNotFoundError("Pedido não encontrado.")
            if payload.item_id is not None and not any(
                item.id == payload.item_id for item in order.items
            ):
                raise LotDraftValidationError("Item não pertence ao pedido informado.")

        message = await self.chat_repository.add_message(
            session.id,
            payload.content or "Rascunho de lote preparado para revisão.",
            role=ChatMessageRole.AGENT,
        )
        draft = LotDraft(
            session_id=session.id,
            message_id=message.id,
            order_id=payload.order_id,
            item_id=payload.item_id,
            producer_id=payload.producer_id,
            quantity=payload.quantity,
            unit=payload.unit,
            delivery_date=payload.delivery_date,
            availability_confirmed=bool(payload.availability_confirmed),
            needs_date_review=False,
            status="em_revisao",
            revision=1,
        )
        self.draft_repository.add(draft)
        await self.draft_repository.session.commit()

        loaded = await self.draft_repository.get_by_id(draft.id)
        assert loaded is not None
        message.lot_draft = loaded
        return message, loaded

    async def update_draft(
        self,
        draft_id: UUID,
        user: User,
        payload: LotDraftUpdate,
    ) -> LotDraft:
        draft = await self._get_locked_draft(draft_id, user)
        if draft.status == "confirmado" or draft.lot_id is not None:
            raise LotDraftConflictError(
                "Este rascunho já foi autorizado e não pode mais ser editado."
            )

        updates = payload.model_dump(exclude_unset=True)
        prev_order_id = draft.order_id
        prev_item_id = draft.item_id
        prev_producer_id = draft.producer_id
        prev_quantity = draft.quantity
        prev_unit = draft.unit
        prev_delivery_date = draft.delivery_date

        next_order_id = updates.get("order_id", draft.order_id)
        next_item_id = updates.get("item_id", draft.item_id)

        order_changed = next_order_id != prev_order_id
        item_changed = next_item_id != prev_item_id

        if order_changed and "item_id" not in updates:
            next_item_id = None

        if next_order_id is not None:
            order = await self.order_repository.get_by_id(next_order_id, lock=False)
            if order is None:
                raise LotDraftNotFoundError("Pedido não encontrado.")
            if next_item_id is not None and not any(
                item.id == next_item_id for item in order.items
            ):
                raise LotDraftValidationError("Item não pertence ao pedido selecionado.")

        draft.order_id = next_order_id
        draft.item_id = next_item_id
        if "producer_id" in updates:
            draft.producer_id = updates["producer_id"]
        if "quantity" in updates:
            draft.quantity = updates["quantity"]
        if "unit" in updates:
            draft.unit = updates["unit"]
        if "delivery_date" in updates:
            draft.delivery_date = updates["delivery_date"]

        availability_relevant_changed = (
            draft.producer_id != prev_producer_id
            or draft.quantity != prev_quantity
            or draft.unit != prev_unit
            or draft.delivery_date != prev_delivery_date
            or order_changed
            or item_changed
        )
        if availability_relevant_changed:
            draft.availability_confirmed = False

        if order_changed or item_changed:
            draft.needs_date_review = True
        elif "delivery_date" in updates and draft.delivery_date is not None:
            draft.needs_date_review = False

        draft.revision += 1
        await self.draft_repository.session.commit()
        loaded = await self.draft_repository.get_by_id(draft.id)
        assert loaded is not None
        return loaded

    async def set_availability(
        self,
        draft_id: UUID,
        user: User,
        payload: LotDraftAvailabilityUpdate,
    ) -> LotDraft:
        draft = await self._get_locked_draft(draft_id, user)
        if draft.status == "confirmado" or draft.lot_id is not None:
            raise LotDraftConflictError(
                "Este rascunho já foi autorizado e não pode mais ser alterado."
            )

        self._assert_expected_revision(draft, payload.expected_revision)

        if payload.confirmed and (
            draft.order_id is None
            or draft.item_id is None
            or draft.producer_id is None
            or draft.quantity is None
            or not draft.unit
            or draft.delivery_date is None
        ):
            raise LotDraftValidationError(
                "Preencha pedido, item, produtor, quantidade, unidade e data "
                "prevista antes de confirmar a disponibilidade."
            )

        if payload.confirmed and draft.needs_date_review:
            raise LotDraftValidationError(
                "Revise e salve a data prevista do lote conforme o prazo do pedido "
                "antes de confirmar a disponibilidade."
            )

        draft.availability_confirmed = payload.confirmed
        draft.revision += 1
        await self.draft_repository.session.commit()
        loaded = await self.draft_repository.get_by_id(draft.id)
        assert loaded is not None
        return loaded

    async def confirm_draft(
        self,
        draft_id: UUID,
        user: User,
        payload: LotDraftConfirmRequest | None = None,
    ) -> LotDraft:
        draft = await self._get_locked_draft(draft_id, user)

        if draft.lot_id is not None:
            loaded = await self.draft_repository.get_by_id(draft.id)
            assert loaded is not None
            return loaded

        if draft.status == "confirmado":
            raise LotDraftConflictError(
                "Esta autorização já foi processada anteriormente e o lote "
                "correspondente não está mais ativo. Crie um novo rascunho se "
                "desejar cadastrar outro lote."
            )

        expected_revision = payload.expected_revision if payload is not None else None
        self._assert_expected_revision(draft, expected_revision)

        if draft.order_id is None or draft.item_id is None:
            raise LotDraftValidationError(
                "Selecione o pedido e o item do pedido antes de autorizar o cadastro."
            )
        if draft.needs_date_review:
            raise LotDraftValidationError(
                "Revise e salve a data prevista do lote conforme o prazo do pedido "
                "antes de autorizar o cadastro."
            )
        if draft.producer_id is None:
            raise LotDraftValidationError(
                "Selecione o produtor antes de autorizar o cadastro."
            )
        if draft.quantity is None or draft.quantity <= 0:
            raise LotDraftValidationError(
                "Informe uma quantidade válida maior que zero."
            )
        if not draft.unit or not draft.unit.strip():
            raise LotDraftValidationError("Informe a unidade do lote.")
        if draft.delivery_date is None:
            raise LotDraftValidationError(
                "Informe a data prevista de entrega do lote."
            )
        if not draft.availability_confirmed:
            raise LotDraftValidationError(
                "Confirme a disponibilidade para os dados revisados antes de "
                "autorizar o cadastro."
            )

        try:
            lot = await self.lot_service.create(
                draft.order_id,
                draft.item_id,
                LotCreate(
                    producer_id=draft.producer_id,
                    quantity=draft.quantity,
                    unit=draft.unit,
                    delivery_date=draft.delivery_date,
                    availability_confirmed=True,
                ),
                commit=False,
            )
            draft.lot_id = lot.id
            draft.status = "confirmado"
            draft.needs_date_review = False
            draft.revision += 1
            await self.draft_repository.session.commit()
        except (LotNotFoundError, LotValidationError, LotConflictError):
            await self.draft_repository.session.rollback()
            raise
        except Exception:
            await self.draft_repository.session.rollback()
            raise

        loaded = await self.draft_repository.get_by_id(draft.id)
        assert loaded is not None
        return loaded

    @staticmethod
    def _assert_expected_revision(
        draft: LotDraft,
        expected_revision: int | None,
    ) -> None:
        if expected_revision is not None and draft.revision != expected_revision:
            raise LotDraftConflictError(
                "Este rascunho foi alterado por outra requisição. Revise os dados "
                "atualizados antes de confirmar."
            )

    async def _get_authorized_session(
        self,
        session_id: UUID,
        user: User,
    ) -> ChatSession:
        session = await self.chat_repository.get_session(session_id, user.id)
        if session is None:
            raise LotDraftNotFoundError("Sessão de chat não encontrada.")
        return session

    async def _get_locked_draft(
        self,
        draft_id: UUID,
        user: User,
    ) -> LotDraft:
        draft = await self.draft_repository.get_by_id(
            draft_id,
            lock=True,
            with_relations=False,
        )
        if draft is None:
            raise LotDraftNotFoundError("Rascunho de lote não encontrado.")

        session = await self.chat_repository.get_session(
            draft.session_id,
            user.id,
        )
        if session is None:
            raise LotDraftNotFoundError("Rascunho de lote não encontrado.")
        return draft

    @staticmethod
    def to_out(draft: LotDraft) -> LotDraftOut:
        return build_lot_draft_out(draft)
