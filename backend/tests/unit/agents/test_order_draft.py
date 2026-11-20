from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from api.agents.triage import (
    TriageAnalysis,
    TriageInput,
    analyze_order_draft,
    prepare_order_draft,
)
from api.schemas.order_draft import OrderDraftData
from api.schemas.product import ProductResponse
from tests.unit.agents.test_triage import FakeRunner

MESSAGE = "Precisamos de 10 kg de queijo coalho e, se tiver, 5 potes de mel. Entrega pela manhã, entre 4 e 8 de novembro de 2026."


def analysis(**changes):
    payload = {
        "summary": "Pedido de queijo coalho e mel condicional.",
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
                {"product": "Queijo coalho", "quantity": 10, "unit": "kg"},
                {
                    "product": "Mel",
                    "quantity": 5,
                    "unit": "potes",
                    "conditional": True,
                    "condition_text": "se tiver",
                },
            ],
        },
    }
    data = {**payload["extracted_data"], **changes.pop("extracted_data", {})}
    return TriageAnalysis.model_validate({**payload, **changes, "extracted_data": data})


@pytest.fixture
def products():
    return [ProductResponse(id=uuid4(), name=name) for name in ["Queijo coalho", "Mel"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("store_in_state", [True, False])
async def test_agent_output_matches_issue_10_contract(products, store_in_state):
    runner = FakeRunner(analysis(), store_in_state=store_in_state)
    draft = await analyze_order_draft(
        TriageInput(
            message_text=MESSAGE,
            received_at="2026-10-30",
            buyer_name="Mercado Bom Preço",
        ),
        products=products,
        runner=runner,
    )
    assert OrderDraftData.model_validate_json(draft.model_dump_json()) == draft
    assert draft.buyer == "Mercado Bom Preço"
    assert draft.delivery_start_date == date(2026, 11, 4)
    assert draft.delivery_end_date == date(2026, 11, 8)
    assert "pela manhã" in draft.conditions
    assert [
        (item.product_id, item.quantity, item.unit, item.conditional)
        for item in draft.items
    ] == [
        (products[0].id, Decimal(10), "kg", False),
        (products[1].id, Decimal(5), "potes", True),
    ]
    assert draft.items[1].condition_text == "se tiver"
    assert draft.pending == []
    assert all(item.pending == [] for item in draft.items)
    assert MESSAGE in runner.last_message_text


@pytest.mark.parametrize(
    "request_type", ["consulta", "oferta", "comunicado", "nao_identificado"]
)
def test_non_orders_do_not_generate_drafts(request_type):
    assert prepare_order_draft(analysis(request_type=request_type)) is None


def test_single_date_and_all_conditions_are_preserved(products):
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "delivery_date_start": "2026-11-06",
                "delivery_date_end": None,
                "delivery_location": "Sede",
                "payment_terms": "30 dias",
                "supply_frequency": "semanal",
                "contract_reference": "Contrato 045",
                "general_conditions": ["Transporte refrigerado"],
                "requirements": [
                    {
                        "description": "Certificado orgânico",
                        "verification_needed": "Conferir validade.",
                    }
                ],
            }
        ),
        products=products,
    )
    assert draft.delivery_start_date == date(2026, 11, 6)
    assert draft.delivery_end_date is None
    for value in [
        "pela manhã",
        "Sede",
        "30 dias",
        "semanal",
        "Contrato 045",
        "Transporte refrigerado",
        "Certificado orgânico",
    ]:
        assert value in draft.conditions
    assert "Conferir validade." in draft.pending


def test_missing_data_and_original_pending_are_explicit():
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "buyer_name": " ",
                "delivery_date_start": None,
                "delivery_date_end": None,
                "items": [{"product": "Queijo", "quantity": None, "unit": None}],
            },
            pending_items=[
                {
                    "category": "outro",
                    "description": "Embalagem indefinida.",
                    "question_for_staff": "Qual embalagem usar?",
                }
            ],
        )
    )
    assert draft.buyer is draft.delivery_start_date is None
    for value in ["comprador", "entrega", "Qual embalagem usar?"]:
        assert any(value in text for text in draft.pending)
    item = draft.items[0]
    assert item.product_id is item.quantity is item.unit is None
    for value in ["catálogo", "quantidade", "unidade"]:
        assert any(value in text for text in item.pending)


@pytest.mark.parametrize("quantity", [None, 15])
def test_aggregate_quantity_is_not_guessed(quantity):
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "items": [
                    {
                        "product": "Queijo",
                        "quantity": quantity,
                        "quantity_raw": "uns 15 kg",
                        "unit": "kg",
                        "ambiguous_or_aggregate": True,
                        "clarification_needed": "Qual a quantidade exata?",
                    }
                ]
            }
        )
    )
    assert draft.items[0].quantity is None
    assert any("uns 15 kg" in text for text in draft.items[0].pending)
    assert "Qual a quantidade exata?" in draft.items[0].pending


@pytest.mark.parametrize("quantity", [1.1234, 1e20, float("inf"), float("nan")])
def test_unrepresentable_quantities_require_review(quantity):
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "items": [{"product": "Queijo", "quantity": quantity, "unit": "kg"}]
            }
        )
    )
    assert draft.items[0].quantity is None
    assert any("quantidade válida" in text for text in draft.items[0].pending)


def test_catalog_does_not_guess_unknown_or_ambiguous_products(products):
    draft = prepare_order_draft(
        analysis(), products=[products[1], ProductResponse(id=uuid4(), name="MEL")]
    )
    assert all(item.product_id is None for item in draft.items)
    assert all(any("catálogo" in text for text in item.pending) for item in draft.items)


def test_catalog_normalizes_case_and_whitespace(products):
    products[0].name = "  QUEIJO   COALHO  "
    assert (
        prepare_order_draft(analysis(), products=products).items[0].product_id
        == products[0].id
    )


def test_delivery_conflicts_stay_pending():
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "delivery_date_start": None,
                "delivery_date_end": None,
                "deadlines": [
                    {
                        "action": "entrega",
                        "has_conflict": True,
                        "reference_raw": "sexta ou sábado",
                    }
                ],
            }
        )
    )
    assert draft.delivery_start_date is draft.delivery_end_date is None
    assert any("sexta ou sábado" in text for text in draft.pending)


def test_response_date_does_not_become_delivery():
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "delivery_date_start": None,
                "delivery_date_end": None,
                "response_deadline": "2026-11-01",
            }
        )
    )
    assert draft.delivery_start_date is draft.delivery_end_date is None
    assert any("entrega" in text for text in draft.pending)


def test_empty_order_and_missing_condition_require_confirmation():
    empty = prepare_order_draft(analysis(extracted_data={"items": []}))
    assert any("produtos" in text for text in empty.pending)
    draft = prepare_order_draft(
        analysis(extracted_data={"items": [{"product": "Mel", "conditional": True}]})
    )
    assert draft.items[0].conditional is True
    assert draft.items[0].condition_text is None
    assert any("condição" in text for text in draft.items[0].pending)


def test_conversion_preserves_source_analysis(products):
    original = analysis()
    before = original.model_dump()
    prepare_order_draft(original, products=products)
    assert original.model_dump() == before


def test_blank_product_name_remains_pending():
    draft = prepare_order_draft(analysis(extracted_data={"items": [{"product": " "}]}))
    assert draft.items[0].product_name is None
    assert draft.items[0].product_id is None
    assert "Confirmar qual produto foi solicitado." in draft.items[0].pending


@pytest.mark.parametrize(
    "condition",
    [
        "com certificação orgânica",
        "com laudo sanitário e nota fiscal",
        "temperatura entre 2,5 e 4 graus",
    ],
)
def test_item_fulfillment_requirements_are_added_to_order_conditions(condition):
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "items": [
                    {
                        "product": "Mel silvestre",
                        "quantity": 20,
                        "unit": "kg",
                        "condition_text": condition,
                    }
                ]
            }
        )
    )
    assert draft.items[0].condition_text == condition
    assert draft.items[0].conditional is False
    assert "Exigência para 'Mel silvestre':" in draft.conditions
    assert condition in draft.conditions


@pytest.mark.parametrize(
    "condition", ["se tiver", "Se tiver.", "se houver disponibilidade"]
)
def test_inclusion_conditions_do_not_become_fulfillment_requirements(condition):
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "items": [
                    {
                        "product": "Mel",
                        "quantity": 5,
                        "unit": "potes",
                        "conditional": True,
                        "condition_text": condition,
                    }
                ]
            }
        )
    )
    assert draft.items[0].conditional is True
    assert draft.items[0].condition_text == condition
    assert "Exigência" not in draft.conditions
    assert condition not in draft.conditions


@pytest.mark.parametrize(
    "condition",
    [
        "se tiver, com certificação orgânica",
        "com certificação orgânica e se houver",
    ],
)
def test_mixed_conditions_preserve_requirement_separately_from_inclusion(condition):
    draft = prepare_order_draft(
        analysis(
            extracted_data={
                "items": [
                    {
                        "product": "Mel",
                        "quantity": 5,
                        "unit": "potes",
                        "conditional": True,
                        "condition_text": condition,
                    }
                ]
            }
        )
    )
    assert draft.items[0].conditional is True
    assert draft.items[0].condition_text == condition
    assert "Exigência para 'Mel': com certificação orgânica" in draft.conditions
    assert "se tiver" not in draft.conditions
    assert "se houver" not in draft.conditions
