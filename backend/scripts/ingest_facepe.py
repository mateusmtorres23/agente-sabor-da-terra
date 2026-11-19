import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from api.database import get_session_maker
from api.dependencies import get_triage_task_queue
from api.schemas.triage import ReceivedEntryIngestRequest
from api.services.triage import TriageWorkflowService


def _resolve_pedidos_path(explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path)

    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "pedidos.json",
        repo_root / "docs" / "pedidos.json",
        repo_root / "backend" / "pedidos.json",
        repo_root / "backend" / "data" / "pedidos.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Arquivo pedidos.json não encontrado.")


def _parse_record(record: dict[str, Any]) -> ReceivedEntryIngestRequest:
    external_id = str(
        record.get("id")
        or record.get("pedido_id")
        or record.get("codigo")
    ).strip()
    sender = str(
        record.get("remetente")
        or record.get("sender")
        or record.get("comprador")
    ).strip()
    channel = str(
        record.get("canal")
        or record.get("canal_origem")
        or record.get("source_channel")
    ).strip()
    raw_received_at = (
        record.get("data_recebimento")
        or record.get("received_at")
    )
    message_text = str(
        record.get("mensagem")
        or record.get("texto")
        or record.get("texto_original")
        or record.get("original_text")
    ).strip()

    received_at = (
        datetime.fromisoformat(raw_received_at)
        if isinstance(raw_received_at, str)
        else raw_received_at
    )

    return ReceivedEntryIngestRequest(
        message_text=message_text,
        sender=sender,
        source_channel=channel,
        received_at=received_at,
        source_context="facepe:pedidos.json",
        external_id=external_id,
    )


async def ingest_facepe_file(file_path: Path) -> None:
    raw_data = json.loads(file_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = (
        raw_data["pedidos"] if isinstance(raw_data, dict) else raw_data
    )

    session_maker = get_session_maker()
    task_queue = get_triage_task_queue()

    for record in records:
        payload = _parse_record(record)
        async with session_maker() as session:
            service = TriageWorkflowService(session, task_queue=task_queue)
            entry, solicitation, enqueued = await service.ingest_entry(payload)
            status_info = (
                f"solicitation={solicitation.id}"
                if solicitation
                else f"status={entry.triage_status.value}, enqueued={enqueued}"
            )
            print(
                f"[{payload.external_id}] entry_id={entry.id} "
                f"canal={entry.source_channel} recebido_em={entry.received_at.isoformat()} -> {status_info}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingere os registros de pedidos.json da Facepe pela entrada comum."
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Caminho opcional para pedidos.json",
    )
    args = parser.parse_args()
    pedidos_path = _resolve_pedidos_path(args.file)
    asyncio.run(ingest_facepe_file(pedidos_path))


if __name__ == "__main__":
    main()