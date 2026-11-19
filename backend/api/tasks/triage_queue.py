import asyncio
import json
from typing import Protocol
from uuid import UUID

from google.cloud import tasks_v2


class TriageTaskQueue(Protocol):
    async def enqueue_triage(
        self,
        entry_id: UUID,
        *,
        attempt_token: UUID | None = None,
    ) -> None: ...


class CloudTasksTriageQueue:
    def __init__(
        self,
        *,
        queue_path: str,
        worker_base_url: str,
        service_account_email: str,
        client: tasks_v2.CloudTasksClient | None = None,
    ) -> None:
        self.queue_path = queue_path
        self.worker_base_url = worker_base_url.rstrip("/")
        self.service_account_email = service_account_email
        self._client = client or tasks_v2.CloudTasksClient()

    async def enqueue_triage(
        self,
        entry_id: UUID,
        *,
        attempt_token: UUID | None = None,
    ) -> None:
        target_url = f"{self.worker_base_url}/triage/entries/{entry_id}/process"
        payload = {
            "entry_id": str(entry_id),
            "attempt_token": str(attempt_token) if attempt_token else None,
        }
        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=target_url,
                headers={"Content-Type": "application/json"},
                body=json.dumps(payload).encode("utf-8"),
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=self.service_account_email,
                    audience=self.worker_base_url,
                ),
            )
        )
        await asyncio.to_thread(
            self._client.create_task,
            parent=self.queue_path,
            task=task,
        )


class DisabledTriageQueue:
    """Usado para simular falha de enfileiramento e testar recuperação via Scheduler."""

    async def enqueue_triage(
        self,
        entry_id: UUID,
        *,
        attempt_token: UUID | None = None,
    ) -> None:
        raise RuntimeError("Enfileiramento desabilitado ou indisponível.")