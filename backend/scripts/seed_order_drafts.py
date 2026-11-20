"""Cria cenários locais de revisão de pedidos, sem cadastrar pedidos finais.

Execute em backend/: uv run python -m scripts.seed_order_drafts
"""

import argparse
import asyncio
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_engine, get_session_maker
from api.models.chat_message import ChatMessageRole
from api.models.chat_session import ChatSession
from api.models.order import Order
from api.models.order_draft import OrderDraft
from api.models.product import Product
from api.models.solicitation import (
    Solicitation,
    SolicitationStatus,
    SolicitationType,
    SolicitationUrgency,
)
from api.models.user import User
from api.repositories.chat import ChatRepository
from api.schemas.order_draft import OrderDraftData

NAMESPACE = UUID("74ba0244-8528-4b06-9546-066982a66be8")
MESSAGE = (
    "O Mercado Bom Preço quer 10 kg de queijo coalho e, se tiver, "
    "5 potes de mel. Entregar pela manhã, entre 4 e 8 de novembro de 2026."
)


async def product(session: AsyncSession, name: str) -> Product:
    existing = await session.scalar(
        select(Product)
        .where(func.lower(Product.name) == name.lower())
        .order_by(Product.id)
        .limit(1)
    )
    if existing is not None:
        return existing
    created = Product(name=name)
    session.add(created)
    await session.flush()
    return created


async def seed(session: AsyncSession, email: str, scenario: str) -> list[dict]:
    # O bloqueio serializa duas execuções para o mesmo usuário.
    user = await session.scalar(
        select(User).where(User.email == email).with_for_update(of=User)
    )
    if user is None:
        raise ValueError("Usuário não encontrado. Informe o e-mail usado no login.")

    cheese = await product(session, "Queijo coalho")
    honey = await product(session, "Mel")
    result = []
    for kind in ("private", "triage"):
        identifier = f"issue10:{user.id}:{scenario}:{kind}"
        chat_id = uuid5(NAMESPACE, f"{identifier}:chat")
        draft_id = uuid5(NAMESPACE, f"{identifier}:draft")
        solicitation_id = uuid5(NAMESPACE, f"{identifier}:solicitation")
        title = f"[Teste #10 {scenario}] Mercado Bom Preço"
        chat = await session.get(ChatSession, chat_id)
        if chat is None:
            chat = ChatSession(
                id=chat_id,
                user_id=user.id if kind == "private" else None,
                title=title,
            )
            session.add(chat)
            await session.flush()
            repository = ChatRepository(session)
            await repository.add_message(chat_id, MESSAGE)
            await repository.add_message(
                chat_id,
                "Rascunho de teste disponível na seção Pedido desta conversa. "
                "Revise o mel condicional e o prazo antes de confirmar.",
                role=ChatMessageRole.AGENT,
            )
        if (
            kind == "triage"
            and await session.get(Solicitation, solicitation_id) is None
        ):
            session.add(
                Solicitation(
                    id=solicitation_id,
                    session_id=chat_id,
                    status=SolicitationStatus.RECEIVED,
                    summary=f"{title}: 10 kg de queijo coalho e mel condicional.",
                    request_type=SolicitationType.ORDER,
                    urgency=SolicitationUrgency.NORMAL,
                )
            )
        draft = await session.get(OrderDraft, draft_id)
        if draft is None:
            data = OrderDraftData.model_validate(
                {
                    "buyer": "Mercado Bom Preço",
                    "conditions": "Entrega pela manhã.",
                    "delivery_start_date": "2026-11-04",
                    "delivery_end_date": "2026-11-08",
                    "items": [
                        {
                            "id": uuid5(NAMESPACE, f"{identifier}:cheese"),
                            "product_id": cheese.id,
                            "product_name": cheese.name,
                            "quantity": "10",
                            "unit": "kg",
                        },
                        {
                            "id": uuid5(NAMESPACE, f"{identifier}:honey"),
                            "product_id": honey.id,
                            "product_name": honey.name,
                            "quantity": "5",
                            "unit": "pote",
                            "conditional": True,
                            "condition_text": "Se tiver.",
                        },
                    ],
                }
            )
            session.add(
                OrderDraft(
                    id=draft_id,
                    session_id=chat_id,
                    data=data.model_dump(mode="json"),
                )
            )
        order_id = await session.scalar(
            select(Order.id).where(Order.session_id == chat_id)
        )
        result.append(
            {
                "kind": kind,
                "title": title,
                "chat_id": chat_id,
                "draft_id": draft_id,
                "solicitation_id": solicitation_id,
                "order_id": order_id,
            }
        )
    await session.flush()
    return result


async def run(email: str, scenario: str) -> None:
    try:
        async with get_session_maker().begin() as session:
            scenarios = await seed(session, email, scenario)
        print("Cenários disponíveis. Nenhum pedido final foi criado pelo script.")
        for item in scenarios:
            print()
            print("CHAT PRIVADO" if item["kind"] == "private" else "TRIAGEM")
            print(f"  Título: {item['title']}")
            print(f"  Conversa: {item['chat_id']}")
            print(f"  Rascunho: {item['draft_id']}")
            path = (
                "/chat"
                if item["kind"] == "private"
                else f"/triagem/{item['solicitation_id']}"
            )
            print(f"  Abra: http://localhost:5173{path}")
            if item["order_id"]:
                print(f"  Pedido já vinculado: {item['order_id']} (preservado).")
        print(
            "\nReexecutar preserva as revisões, confirmações e finalizações existentes."
        )
        print("Para outro par de cenários: --scenario revisao-2")
    finally:
        await get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cria rascunhos locais para testar a issue #10."
    )
    parser.add_argument(
        "--email", help="E-mail de um usuário já cadastrado no banco local."
    )
    parser.add_argument(
        "--scenario",
        default="revisao-1",
        help="Nome do cenário (máximo 40 caracteres).",
    )
    args = parser.parse_args()
    email = (args.email or input("E-mail usado no login: ")).strip()
    scenario = args.scenario.strip()
    if not email or not scenario or len(scenario) > 40:
        parser.error("Informe o e-mail e um nome de cenário de 1 a 40 caracteres.")
    try:
        asyncio.run(run(email, scenario))
    except ValueError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
