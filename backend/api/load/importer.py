from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Lot, Producer, ProducerProduct, Product
from .parsing import (
    extract_unit,
    parse_active,
    parse_date,
    parse_quantity,
    split_products,
)


@dataclass
class ImportSummary:
    products_created: int = 0
    producers_created: int = 0
    links_created: int = 0
    lots_created: int = 0


async def _get_product(session: AsyncSession, name: str) -> Product | None:
    return await session.scalar(select(Product).where(Product.name == name))


async def _get_producer(session: AsyncSession, code: str) -> Producer | None:
    return await session.scalar(select(Producer).where(Producer.code == code))


async def _get_link(
    session: AsyncSession,
    producer_id: Any,
    product_id: Any,
) -> ProducerProduct | None:
    return await session.scalar(
        select(ProducerProduct).where(
            ProducerProduct.producer_id == producer_id,
            ProducerProduct.product_id == product_id,
        )
    )


async def import_facepe(
    session: AsyncSession,
    producers_rows: list[dict[str, str]],
    lots_rows: list[dict[str, str]],
) -> ImportSummary:
    """Importa o catálogo, os produtores, os vínculos e os lotes históricos.

    Produtos, produtores e vínculos são reaproveitados pelos seus
    identificadores naturais (nome e código), respeitando as restrições de
    unicidade do modelo.
    """
    summary = ImportSummary()

    try:
        products_by_name: dict[str, Product] = {}
        for row in producers_rows:
            for name in split_products(row.get("produtos", "")):
                if name in products_by_name:
                    continue
                product = await _get_product(session, name)
                if product is None:
                    product = Product(name=name)
                    session.add(product)
                    await session.flush()
                    summary.products_created += 1
                products_by_name[name] = product

        producers_by_code: dict[str, Producer] = {}
        for row in producers_rows:
            code = row["id"].strip()
            producer = await _get_producer(session, code)
            if producer is None:
                producer = Producer(
                    code=code,
                    name=row["nome_completo"].strip(),
                    cpf=row["cpf"].strip(),
                    active=parse_active(row["status"]),
                    phone=row["telefone"].strip() or None,
                    email=row["email"].strip() or None,
                    address=row["endereco"].strip() or None,
                    municipality=row["municipio"].strip() or None,
                )
                session.add(producer)
                await session.flush()
                summary.producers_created += 1
            producers_by_code[code] = producer

        for row in producers_rows:
            producer = producers_by_code[row["id"].strip()]
            for name in split_products(row.get("produtos", "")):
                product = products_by_name[name]
                link = await _get_link(session, producer.id, product.id)
                if link is None:
                    session.add(
                        ProducerProduct(
                            producer_id=producer.id,
                            product_id=product.id,
                        )
                    )
                    summary.links_created += 1

        for row in lots_rows:
            code = row["produtor_id"].strip()
            producer = producers_by_code.get(code) or await _get_producer(
                session,
                code,
            )
            if producer is None:
                raise ValueError(
                    f"Produtor {code} não encontrado para o lote "
                    f"{row['lote_id'].strip()}."
                )

            session.add(
                Lot(
                    item_id=None,
                    producer_id=producer.id,
                    quantity=parse_quantity(row["quantidade_kg"]),
                    unit=extract_unit(row.get("observacao")),
                    delivery_date=parse_date(row["data_entrega"]),
                    availability_confirmed=None,
                )
            )
            summary.lots_created += 1

        await session.commit()
        return summary

    except Exception:
        await session.rollback()
        raise
