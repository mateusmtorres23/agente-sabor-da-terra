from datetime import date
from decimal import Decimal

import pytest

from api.load.parsing import (
    extract_unit,
    parse_active,
    parse_date,
    parse_quantity,
    split_products,
)


def test_split_products_trims_and_drops_empty() -> None:
    assert split_products("goiaba, acerola, manga") == [
        "goiaba",
        "acerola",
        "manga",
    ]
    assert split_products("mel silvestre") == ["mel silvestre"]
    assert split_products("") == []
    assert split_products("a,,b") == ["a", "b"]


def test_parse_active() -> None:
    assert parse_active("ativo") is True
    assert parse_active("inativo") is False
    assert parse_active(" ATIVO ") is True


def test_parse_quantity() -> None:
    assert parse_quantity("45") == Decimal(45)
    assert parse_quantity("10,5") == Decimal("10.5")


def test_parse_quantity_rejects_blank() -> None:
    with pytest.raises(ValueError):
        parse_quantity("  ")


def test_parse_date() -> None:
    assert parse_date("2026-09-08") == date(2026, 9, 8)


def test_extract_unit_from_observation() -> None:
    assert extract_unit("300 unidades") == "unidades"
    assert extract_unit("150 maços") == "maços"
    assert extract_unit("80 unidades") == "unidades"


def test_extract_unit_ambiguous_maços_kg() -> None:
    assert extract_unit("40 maços (kg)") is None


def test_extract_unit_returns_none_for_notes_and_empty() -> None:
    assert extract_unit("Certificação orgânica anexa") is None
    assert extract_unit("Abate no dia. Refrigerado.") is None
    assert extract_unit("Sem certificação orgânica") is None
    assert extract_unit("") is None
    assert extract_unit(None) is None
