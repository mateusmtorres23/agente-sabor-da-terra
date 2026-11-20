import re
from collections.abc import Sequence
from decimal import Decimal

from google.adk import Runner
from pydantic import TypeAdapter, ValidationError

from ...schemas.order import Quantity
from ...schemas.order_draft import OrderDraftData, OrderDraftItem
from ...schemas.product import ProductResponse
from .agent import analyze_triage_message
from .schemas import DeadlineAction, RequestType, TriageAnalysis, TriageInput

_QUANTITY = TypeAdapter(Quantity)


def _text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _fulfillment_condition(condition: str) -> str:
    inclusion = (
        r"(?:se (?:tiver|houver)(?: disponibilidade)?|se disponível|"
        r"caso (?:tenha|haja)(?: disponibilidade)?)"
    )
    clauses = re.split(r"\s*[,;](?!\d)\s*|\s+e\s+", condition, flags=re.IGNORECASE)
    requirements = [
        clause.strip()
        for clause in clauses
        if clause.strip()
        and not re.fullmatch(
            inclusion, " ".join(clause.strip(" .!?").split()), flags=re.IGNORECASE
        )
    ]
    return condition if len(requirements) == len(clauses) else "; ".join(requirements)


def prepare_order_draft(
    analysis: TriageAnalysis,
    *,
    products: Sequence[ProductResponse] = (),
) -> OrderDraftData | None:
    if analysis.request_type != RequestType.ORDER:
        return None

    data = analysis.extracted_data
    pending = [
        f"{entry.description} {entry.question_for_staff}"
        for entry in analysis.pending_items
    ]
    buyer = _text(data.buyer_name)
    if buyer is None:
        pending.append("Confirmar o comprador do pedido.")
    if not data.items:
        pending.append("Confirmar os produtos, as quantidades e as unidades do pedido.")

    delivery = next(
        (entry for entry in data.deadlines if entry.action == DeadlineAction.DELIVERY),
        None,
    )
    start = delivery.start_as_date if delivery and not delivery.has_conflict else None
    end = delivery.end_as_date if delivery and not delivery.has_conflict else None
    if start is None:
        reference = (
            f" Referência original: {data.delivery_reference_raw}."
            if data.delivery_reference_raw
            else ""
        )
        pending.append(f"Confirmar a data ou o intervalo de entrega.{reference}")

    conditions = list(data.general_conditions)
    for label, value in (
        ("Horário de entrega", data.delivery_time_window),
        ("Local de entrega", data.delivery_location),
        ("Pagamento", data.payment_terms),
        ("Frequência de fornecimento", data.supply_frequency),
        ("Contrato", data.contract_reference),
    ):
        if _text(value):
            conditions.append(f"{label}: {value.strip()}")
    for requirement in data.requirements:
        conditions.append(requirement.description)
        if _text(requirement.verification_needed):
            pending.append(requirement.verification_needed)

    items = []
    for extracted in data.items:
        name = extracted.product.strip()
        item_pending = []
        if not name:
            item_pending.append("Confirmar qual produto foi solicitado.")
        matches = {
            product.id
            for product in products
            if " ".join(product.name.casefold().split())
            == " ".join(name.casefold().split())
        }
        product_id = next(iter(matches)) if len(matches) == 1 else None
        if product_id is None:
            item_pending.append(
                f"Confirmar o produto do catálogo correspondente a '{name}'."
            )

        quantity = None
        if extracted.quantity is not None:
            try:
                quantity = _QUANTITY.validate_python(Decimal(str(extracted.quantity)))
            except ValidationError:
                item_pending.append(
                    f"Confirmar a quantidade válida de '{name}': {extracted.quantity}."
                )
        if extracted.ambiguous_or_aggregate:
            quantity = None
            item_pending.append(
                f"Confirmar a quantidade individual e a especificação de '{name}'."
            )
        if quantity is None:
            quantity_reference = extracted.quantity_raw or (
                str(extracted.quantity) if extracted.quantity is not None else None
            )
            reference = (
                f" Referência original: {quantity_reference}."
                if quantity_reference
                else ""
            )
            item_pending.append(f"Confirmar a quantidade de '{name}'.{reference}")
        unit = _text(extracted.unit)
        if unit is None:
            item_pending.append(f"Confirmar a unidade de '{name}'.")
        if _text(extracted.clarification_needed):
            item_pending.append(extracted.clarification_needed)
        condition = _text(extracted.condition_text)
        if condition:
            fulfillment = _fulfillment_condition(condition)
            if fulfillment:
                conditions.append(f"Exigência para '{name}': {fulfillment}")
        if extracted.conditional and condition is None:
            item_pending.append(f"Confirmar a condição de inclusão de '{name}'.")
        items.append(
            OrderDraftItem(
                product_id=product_id,
                product_name=name or None,
                quantity=quantity,
                unit=unit,
                conditional=extracted.conditional,
                condition_text=condition,
                pending=_unique(item_pending),
            )
        )

    return OrderDraftData(
        buyer=buyer,
        conditions="\n".join(_unique(conditions)),
        delivery_start_date=start,
        delivery_end_date=end,
        items=items,
        pending=_unique(pending),
    )


async def analyze_order_draft(
    payload: TriageInput,
    *,
    products: Sequence[ProductResponse] = (),
    runner: Runner | None = None,
    model: str | None = None,
) -> OrderDraftData | None:
    analysis = await analyze_triage_message(payload, runner=runner, model=model)
    return prepare_order_draft(analysis, products=products)
