from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from api.schemas.order_draft import OrderDraftConfirmation


def valid_confirmation() -> dict:
    return {
        "draft_version": 1,
        "confirmed": True,
        "buyer": "Mercado Bom Preço",
        "conditions": "Entrega pela manhã",
        "delivery_start_date": "2026-11-06",
        "delivery_end_date": None,
        "items": [
            {
                "draft_item_id": str(uuid4()),
                "product_id": str(uuid4()),
                "quantity": "10",
                "unit": "kg",
            }
        ],
    }


def test_confirmation_converts_reviewed_data_to_order_creation() -> None:
    payload = valid_confirmation()

    confirmation = OrderDraftConfirmation.model_validate(payload)
    order = confirmation.to_order_create()

    assert order.buyer == "Mercado Bom Preço"
    assert order.conditions == "Entrega pela manhã"
    assert order.delivery_start_date == date(2026, 11, 6)
    assert order.delivery_end_date is None

    assert len(order.items) == 1
    assert order.items[0].quantity == Decimal(10)
    assert order.items[0].unit == "kg"
    assert str(order.items[0].product_id) == (
        payload["items"][0]["product_id"]
    )

    serialized = order.model_dump(mode="json")

    assert "draft_version" not in serialized
    assert "confirmed" not in serialized
    assert "draft_item_id" not in serialized["items"][0]


@pytest.mark.parametrize("version", [0, -1, True, "1"])
def test_confirmation_rejects_invalid_version(version) -> None:
    payload = valid_confirmation()
    payload["draft_version"] = version

    with pytest.raises(ValidationError):
        OrderDraftConfirmation.model_validate(payload)


@pytest.mark.parametrize("confirmed", [False, 1, "true"])
def test_confirmation_requires_explicit_boolean_true(confirmed) -> None:
    payload = valid_confirmation()
    payload["confirmed"] = confirmed

    with pytest.raises(ValidationError):
        OrderDraftConfirmation.model_validate(payload)


def test_confirmation_rejects_duplicate_draft_item_ids() -> None:
    payload = valid_confirmation()
    payload["items"].append(dict(payload["items"][0]))

    with pytest.raises(ValidationError):
        OrderDraftConfirmation.model_validate(payload)


def test_confirmation_requires_the_source_draft_item_id() -> None:
    payload = valid_confirmation()
    del payload["items"][0]["draft_item_id"]

    with pytest.raises(ValidationError):
        OrderDraftConfirmation.model_validate(payload)