import csv
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.load import import_facepe
from api.load.parsing import split_products
from api.models import Lot, Order, OrderItem, Producer, ProducerProduct, Product

pytestmark = pytest.mark.asyncio

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def facepe_files() -> tuple[Path, Path]:
    producers = DATA_DIR / "produtores.csv"
    lots = DATA_DIR / "lotes.csv"
    if not producers.exists() or not lots.exists():
        pytest.skip("Arquivos da base Facepe ausentes.")
    return producers, lots


async def _count(session: AsyncSession, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def _lot_by(
    session: AsyncSession,
    producer_code: str,
    quantity: str,
) -> Lot:
    lot = await session.scalar(
        select(Lot)
        .join(Producer, Producer.id == Lot.producer_id)
        .where(
            Producer.code == producer_code,
            Lot.quantity == Decimal(quantity),
        )
    )
    assert lot is not None
    return lot


async def test_imports_catalog_producers_links_and_lots(
    db_session: AsyncSession,
    facepe_files: tuple[Path, Path],
) -> None:
    producers_rows = _read(facepe_files[0])
    lots_rows = _read(facepe_files[1])

    summary = await import_facepe(db_session, producers_rows, lots_rows)

    expected_products = {
        name
        for row in producers_rows
        for name in split_products(row["produtos"])
    }
    expected_producers = {row["id"].strip() for row in producers_rows}
    expected_links = {
        (row["id"].strip(), name)
        for row in producers_rows
        for name in split_products(row["produtos"])
    }

    assert summary.products_created == len(expected_products)
    assert summary.producers_created == len(expected_producers)
    assert summary.links_created == len(expected_links)
    assert summary.lots_created == len(lots_rows)
    assert len(lots_rows) == 20

    assert await _count(db_session, Product) == len(expected_products)
    assert await _count(db_session, Producer) == len(expected_producers)
    assert await _count(db_session, ProducerProduct) == len(expected_links)
    assert await _count(db_session, Lot) == len(lots_rows)
    assert await _count(db_session, Order) == 0
    assert await _count(db_session, OrderItem) == 0

    product_names = set(await db_session.scalars(select(Product.name)))
    assert product_names == expected_products

    producer_codes = set(await db_session.scalars(select(Producer.code)))
    assert producer_codes == expected_producers

    producers_by_id = {
        producer.id: producer.code
        for producer in await db_session.scalars(select(Producer))
    }
    products_by_id = {
        product.id: product.name
        for product in await db_session.scalars(select(Product))
    }
    actual_links = {
        (producers_by_id[producer_id], products_by_id[product_id])
        for producer_id, product_id in await db_session.execute(
            select(ProducerProduct.producer_id, ProducerProduct.product_id)
        )
    }
    assert actual_links == expected_links


async def test_producers_keep_active_status(
    db_session: AsyncSession,
    facepe_files: tuple[Path, Path],
) -> None:
    await import_facepe(db_session, _read(facepe_files[0]), _read(facepe_files[1]))

    active = await db_session.scalar(
        select(Producer.active).where(Producer.code == "P004")
    )
    inactive = await db_session.scalar(
        select(Producer.active).where(Producer.code == "P015")
    )
    assert active is True
    assert inactive is False


async def test_imported_lots_have_null_item_and_expected_dates_and_units(
    db_session: AsyncSession,
    facepe_files: tuple[Path, Path],
) -> None:
    await import_facepe(db_session, _read(facepe_files[0]), _read(facepe_files[1]))

    lots = list(await db_session.scalars(select(Lot)))
    assert len(lots) == 20
    assert all(lot.item_id is None for lot in lots)
    assert all(lot.availability_confirmed is None for lot in lots)

    alface = await _lot_by(db_session, "P004", "300")
    assert alface.unit == "unidades"
    assert alface.delivery_date.isoformat() == "2026-09-08"

    coentro = await _lot_by(db_session, "P004", "150")
    assert coentro.unit == "maços"
    assert coentro.delivery_date.isoformat() == "2026-09-08"

    couve = await _lot_by(db_session, "P009", "40")
    assert couve.unit is None
    assert couve.delivery_date.isoformat() == "2026-09-15"
