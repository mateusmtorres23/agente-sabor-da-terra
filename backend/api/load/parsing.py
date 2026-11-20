import re
from datetime import date
from decimal import Decimal

_MASS_UNITS = ("kg", "g", "t")
_COUNT_UNITS = (
    "unidades",
    "unidade",
    "maços",
    "maço",
    "caixas",
    "caixa",
    "litros",
    "litro",
    "dúzias",
    "dúzia",
    "duzias",
    "duzia",
)


def split_products(produtos: str) -> list[str]:
    if not produtos:
        return []
    return [item.strip() for item in produtos.split(",") if item.strip()]


def parse_active(status: str) -> bool:
    return status.strip().lower() == "ativo"


def parse_quantity(value: str) -> Decimal:
    normalized = value.strip().replace(",", ".")
    if not normalized:
        raise ValueError("Quantidade ausente.")
    return Decimal(normalized)


def parse_date(value: str) -> date:
    return date.fromisoformat(value.strip())


def extract_unit(observacao: str | None) -> str | None:
    """Extrai a unidade da observação, devolvendo None quando ausente ou ambígua.

    O nome da coluna ``quantidade_kg`` não define a unidade: ela vem da
    observação, como em "300 unidades" ou "150 maços". Descrições com duas
    unidades distintas, como "40 maços (kg)", são ambíguas e retornam None.
    """
    if not observacao:
        return None

    text = observacao.strip().lower()
    if not text:
        return None

    units = [
        unit
        for unit in (*_MASS_UNITS, *_COUNT_UNITS)
        if re.search(rf"\b{re.escape(unit)}\b", text)
    ]

    if not units:
        return None

    families = {"massa" if unit in _MASS_UNITS else "contagem" for unit in units}
    if len(families) > 1:
        return None

    return units[0]
