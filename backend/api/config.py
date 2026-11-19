
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_DOCUMENT_UPLOAD_MAX_BYTES = 10 * 1024**2
MAX_DOCUMENT_UPLOAD_BYTES = 30 * 1024**2


def get_document_upload_max_bytes() -> int:
    max_bytes = globals()["MAX_DOCUMENT_UPLOAD_BYTES"]

    configured = os.getenv("DOCUMENT_UPLOAD_MAX_BYTES")
    if configured is None:
        return DEFAULT_DOCUMENT_UPLOAD_MAX_BYTES

    error_message = (
        f"DOCUMENT_UPLOAD_MAX_BYTES must be between 1 and {max_bytes}."
    )
    try:
        limit = int(configured)
    except ValueError as error:
        raise RuntimeError(error_message) from error

    if not 1 <= limit <= max_bytes:
        raise RuntimeError(error_message)

    return limit


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url or not url.strip():
        raise RuntimeError("DATABASE_URL must be set.")
    return url.strip()


def get_cors_allowed_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    return [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip()
    ]


def get_document_storage_backend() -> Literal["local", "gcs"]:
    backend = os.getenv("DOCUMENT_STORAGE_BACKEND", "local").strip()
    if backend == "local" or backend == "gcs":
        return backend
    raise RuntimeError("DOCUMENT_STORAGE_BACKEND must be 'local' or 'gcs'.")


def get_document_storage_dir() -> Path:
    directory = os.getenv("DOCUMENT_STORAGE_DIR", "").strip()
    if not directory:
        raise RuntimeError("DOCUMENT_STORAGE_DIR must be set.")
    return Path(directory)


def get_document_storage_bucket() -> str:
    bucket = os.getenv("DOCUMENT_STORAGE_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("DOCUMENT_STORAGE_BUCKET must be set.")
    return bucket
def get_triage_queue_backend() -> Literal["cloud_tasks", "inline", "disabled"]:
    backend = os.getenv("TRIAGE_QUEUE_BACKEND", "inline").strip()
    if backend in {"cloud_tasks", "inline", "disabled"}:
        return backend  # type: ignore[return-value]
    raise RuntimeError(
        "TRIAGE_QUEUE_BACKEND must be 'cloud_tasks', 'inline', or 'disabled'."
    )


def get_cloud_tasks_queue_path() -> str:
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
    location = os.getenv("CLOUD_TASKS_LOCATION", "us-central1").strip()
    queue = os.getenv("CLOUD_TASKS_QUEUE", "triage-queue").strip()
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT must be set for Cloud Tasks.")
    return f"projects/{project}/locations/{location}/queues/{queue}"


def get_triage_worker_url() -> str:
    base_url = os.getenv("TRIAGE_WORKER_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TRIAGE_WORKER_BASE_URL must be set for Cloud Tasks.")
    return base_url


def get_triage_worker_service_account() -> str:
    email = os.getenv("TRIAGE_WORKER_SERVICE_ACCOUNT_EMAIL", "").strip()
    if not email:
        raise RuntimeError(
            "TRIAGE_WORKER_SERVICE_ACCOUNT_EMAIL must be set for Cloud Tasks."
        )
    return email


def get_triage_worker_token() -> str | None:
    token = os.getenv("TRIAGE_WORKER_TOKEN", "").strip()
    return token or None