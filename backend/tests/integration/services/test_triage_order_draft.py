from datetime import date
from decimal import Decimal

import pytest

from api.agents.triage import TriageAnalysis, prepare_order_draft
from api.models.product import Product
from api.schemas.order_draft import OrderDraftConfirmation
from api.schemas.product import ProductResponse
from tests.integration.services import test_order_draft

case = test_order_draft.case
service = test_order_draft.service

pytestmark = pytest.mark.asyncio


async def test_generated_draft_can_be_reviewed_and_confirmed_with_issue_10(case):
    async with case.factory() as session:
        catalog = [
            ProductResponse.model_validate(await session.get(Product, product_id))
            for product_id in case.products
        ]
        analysis = TriageAnalysis.model_validate(
            {
                "summary": "Pedido Mercado Bom Preço.",
                "request_type": "pedido",
                "urgency": "normal",
                "urgency_reason": "Entrega em novembro.",
                "received_date_reference": "2026-10-30",
                "extracted_data": {
                    "buyer_name": "Mercado Bom Preço",
                    "delivery_date_start": "2026-11-04",
                    "delivery_date_end": "2026-11-08",
                    "delivery_time_window": "pela manhã",
                    "items": [
                        {"product": catalog[0].name, "quantity": 10, "unit": "kg"},
                        {
                            "product": catalog[1].name,
                            "quantity": 5,
                            "unit": "potes",
                            "conditional": True,
                            "condition_text": "se tiver",
                        },
                    ],
                },
            }
        )
        data = prepare_order_draft(analysis, products=catalog)
        draft = await service(session).create_draft(case.owner, data, **case.scope)
        assert draft.confirmed_order_id is None
        assert draft.data["delivery_end_date"] == "2026-11-08"
        assert draft.data["items"][1]["conditional"] is True
        confirmation = OrderDraftConfirmation.model_validate(
            {
                "buyer": data.buyer,
                "conditions": data.conditions,
                "delivery_start_date": "2026-11-06",
                "delivery_end_date": None,
                "draft_version": draft.version,
                "confirmed": True,
                "items": [
                    {
                        "draft_item_id": data.items[0].id,
                        "product_id": data.items[0].product_id,
                        "quantity": data.items[0].quantity,
                        "unit": data.items[0].unit,
                    }
                ],
            }
        )
        order, created = await service(session).confirm(
            case.owner,
            draft.id,
            confirmation,
            **case.scope,
        )
        assert created is True
        assert order.buyer == "Mercado Bom Preço"
        assert order.delivery_start_date == date(2026, 11, 6)
        assert order.delivery_end_date is None
        assert "pela manhã" in order.conditions
        assert len(order.items) == 1
        assert order.items[0].product_id == case.products[0]
        assert order.items[0].quantity == Decimal(10)


async def test_ped_2026_004_honey_certification_survives_order_confirmation(case):
    import json
    from pathlib import Path

    from api.agents.triage import TriageInput, analyze_order_draft
    from api.repositories.order import OrderRepository
    from tests.unit.agents.test_triage import FakeRunner

    records = json.loads(
        (Path(__file__).resolve().parents[3] / "data" / "pedidos.json").read_text(
            encoding="utf-8"
        )
    )
    source = next(record for record in records if record["id"] == "PED-2026-004")
    assert (
        "Mel silvestre (com certificação orgânica): 20kg" in source["mensagem_original"]
    )
    async with case.factory() as session:
        honey = await session.get(Product, case.products[1])
        honey.name = "Mel silvestre"
        await session.commit()
        catalog = [ProductResponse.model_validate(honey)]
        analysis = TriageAnalysis.model_validate(
            {
                "summary": "Fornecimento de mel para alimentação escolar.",
                "request_type": "pedido",
                "urgency": "normal",
                "urgency_reason": "Entrega de 4 a 8 de novembro.",
                "received_date_reference": "2026-10-28",
                "extracted_data": {
                    "buyer_name": source["comprador"],
                    "delivery_date_start": "2026-11-04",
                    "delivery_date_end": "2026-11-08",
                    "delivery_time_window": "das 7h às 12h",
                    "delivery_location": "depósito central, Rua da Educação, 500",
                    "contract_reference": "045/2026-PNAE",
                    "general_conditions": [
                        "Produtos acompanhados das respectivas notas fiscais."
                    ],
                    "items": [
                        {
                            "product": "Mel silvestre",
                            "quantity": 20,
                            "unit": "kg",
                            "condition_text": "com certificação orgânica",
                            "conditional": False,
                        }
                    ],
                },
            }
        )
        data = await analyze_order_draft(
            TriageInput(
                message_text=source["mensagem_original"],
                received_at=source["data_recebimento"],
                buyer_name=source["comprador"],
                source_id=source["id"],
            ),
            products=catalog,
            runner=FakeRunner(analysis),
        )
        assert data.items[0].conditional is False
        assert "certificação orgânica" in data.conditions
        draft = await service(session).create_draft(case.owner, data, **case.scope)
        payload = OrderDraftConfirmation.model_validate(
            {
                "buyer": data.buyer,
                "conditions": data.conditions,
                "delivery_start_date": data.delivery_start_date,
                "delivery_end_date": data.delivery_end_date,
                "draft_version": draft.version,
                "confirmed": True,
                "items": [
                    {
                        "draft_item_id": item.id,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "unit": item.unit,
                    }
                    for item in data.items
                ],
            }
        )
        order, created = await service(session).confirm(
            case.owner, draft.id, payload, **case.scope
        )
        assert created is True
        order_id = order.id
    async with case.factory() as session:
        saved = await OrderRepository(session).get_by_id(order_id)
        assert saved.buyer == source["comprador"]
        assert saved.delivery_start_date == date(2026, 11, 4)
        assert saved.delivery_end_date == date(2026, 11, 8)
        assert (
            "Exigência para 'Mel silvestre': com certificação orgânica"
            in saved.conditions
        )
        assert "notas fiscais" in saved.conditions
        assert len(saved.items) == 1
        assert saved.items[0].product_id == case.products[1]
        assert saved.items[0].quantity == Decimal(20)
        assert saved.items[0].unit == "kg"
