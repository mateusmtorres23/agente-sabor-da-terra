import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.database import get_session_maker
from api.load import import_facepe

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


async def run(data_dir: Path) -> None:
    producers_rows = read_csv(data_dir / "produtores.csv")
    lots_rows = read_csv(data_dir / "lotes.csv")

    session_maker = get_session_maker()
    async with session_maker() as session:
        summary = await import_facepe(session, producers_rows, lots_rows)

    print("Carga da base Facepe concluída:")
    print(f"  produtos criados:   {summary.products_created}")
    print(f"  produtores criados: {summary.producers_created}")
    print(f"  vínculos criados:   {summary.links_created}")
    print(f"  lotes criados:      {summary.lots_created}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa o catálogo e os lotes históricos da base Facepe.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Diretório com produtores.csv e lotes.csv (padrão: backend/data).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.data_dir))


if __name__ == "__main__":
    main()
