from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.schemas.order_draft import OrderDraftData, OrderDraftItem


def test_empty_draft_accepts_missing_information() -> None:
    draft = OrderDraftData()

    assert draft.buyer is None
    assert draft.delivery_start_date is None
    assert draft.items == []
    assert draft.pending == []


def test_shared_scenario_preserves_conditions_and_conditional_item() -> None:
    draft = OrderDraftData.model_validate(
        {
            "buyer": "Mercado Bom Preço",
            "conditions": "Entrega pela manhã",
            "delivery_start_date": "2026-11-04",
            "delivery_end_date": "2026-11-08",
            "items": [
                {
                    "product_name": "Queijo coalho",
                    "quantity": "10",
                    "unit": "kg",
                },
                {
                    "product_name": "Mel",
                    "quantity": "5",
                    "unit": "potes",
                    "conditional": True,
                    "condition_text": "se tiver",
                },
            ],
        }
    )

    assert draft.buyer == "Mercado Bom Preço"
    assert draft.conditions == "Entrega pela manhã"
    assert draft.delivery_start_date == date(2026, 11, 4)
    assert draft.delivery_end_date == date(2026, 11, 8)

    cheese, honey = draft.items

    assert cheese.product_name == "Queijo coalho"
    assert cheese.quantity == Decimal(10)
    assert cheese.unit == "kg"
    assert cheese.conditional is False

    assert honey.product_name == "Mel"
    assert honey.quantity == Decimal(5)
    assert honey.unit == "potes"
    assert honey.conditional is True
    assert honey.condition_text == "se tiver"

    assert cheese.id != honey.id


def test_item_can_preserve_missing_information_and_pending_notes() -> None:
    item = OrderDraftItem(
        product_name="Mel",
        pending=[
            "Confirmar a quantidade.",
            "Associar ao produto do catálogo.",
        ],
    )

    assert item.product_id is None
    assert item.quantity is None
    assert item.unit is None
    assert len(item.pending) == 2


@pytest.mark.parametrize(
    "quantity",
    ["0", "-1", "NaN", "Infinity", "1.2345"],
)
def test_item_rejects_invalid_quantity(quantity: str) -> None:
    with pytest.raises(ValidationError):
        OrderDraftItem(quantity=quantity)


@pytest.mark.parametrize("unit", ["", "   "])
def test_item_rejects_blank_unit(unit: str) -> None:
    with pytest.raises(ValidationError):
        OrderDraftItem(unit=unit)


def test_draft_rejects_inverted_delivery_dates() -> None:
    with pytest.raises(ValidationError):
        OrderDraftData(
            delivery_start_date=date(2026, 11, 8),
            delivery_end_date=date(2026, 11, 4),
        )


def test_draft_rejects_duplicate_item_ids() -> None:
    item_id = uuid4()

    with pytest.raises(ValidationError):
        OrderDraftData(
            items=[
                OrderDraftItem(id=item_id, product_name="Queijo coalho"),
                OrderDraftItem(id=item_id, product_name="Mel"),
            ]
        )


def test_serialization_preserves_item_ids_and_decimal_precision() -> None:
    original = OrderDraftData(
        items=[
            OrderDraftItem(
                product_id=uuid4(),
                product_name="Queijo coalho",
                quantity=Decimal("10.125"),
                unit="kg",
            )
        ]
    )

    serialized = original.model_dump(mode="json")
    restored = OrderDraftData.model_validate(serialized)

    assert serialized["items"][0]["quantity"] == "10.125"
    assert restored.items[0].id == original.items[0].id
    assert restored.items[0].product_id == original.items[0].product_id
    assert restored.items[0].quantity == Decimal("10.125")


def test_pending_lists_are_independent() -> None:
    first = OrderDraftData()
    second = OrderDraftData()

    first.pending.append("Confirmar comprador.")

    assert second.pending == []