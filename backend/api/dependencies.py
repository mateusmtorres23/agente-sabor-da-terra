from threading import Lock
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.cloud.storage import Client
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Header
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from . import database
from .config import (
    get_document_storage_backend,
    get_document_storage_bucket,
    get_document_storage_dir,
)
from .database import get_db
from .models.user import User
from .repositories.chat import ChatRepository
from .repositories.document import DocumentRepository
from .repositories.order import OrderRepository
from .repositories.producer import ProducerRepository
from .repositories.product import ProductRepository
from .repositories.solicitation import SolicitationRepository
from .repositories.user import UserRepository
from .services.auth import AuthService, InvalidAccessTokenError
from .services.chat import ChatService
from .services.document import DocumentService
from .services.order import OrderService
from .services.producer import ProducerService
from .services.product import ProductService
from .services.solicitation import SolicitationService
from .services.user import UserService
from .storage.base import DocumentStorage
from .storage.gcs import GCSDocumentStorage
from .storage.local import LocalDocumentStorage

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
_gcs_client_lock = Lock()
_gcs_client: Client | None = None


def _get_gcs_client() -> Client:
    global _gcs_client

    with _gcs_client_lock:
        if _gcs_client is None:
            _gcs_client = Client()

        return _gcs_client


def _build_auth_service(session: AsyncSession) -> AuthService:
    user_repository = UserRepository(session)
    user_service = UserService(user_repository)
    return AuthService(user_service)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> AuthService:
    return _build_auth_service(session)


def get_document_storage() -> DocumentStorage:
    if get_document_storage_backend() == "local":
        return LocalDocumentStorage(get_document_storage_dir())

    bucket_name = get_document_storage_bucket()
    return GCSDocumentStorage(_get_gcs_client().bucket(bucket_name))


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
) -> DocumentService:
    return DocumentService(DocumentRepository(session), storage)


def get_chat_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> ChatService:
    return ChatService(ChatRepository(session))


def get_product_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> ProductService:
    return ProductService(ProductRepository(session))


def get_producer_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> ProducerService:
    return ProducerService(ProducerRepository(session))


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    session_maker = database.get_session_maker()

    try:
        async with session_maker() as session:
            user = await _build_auth_service(session).get_current_user(token)
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_order_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrderService:
    repository = OrderRepository(session)
    return OrderService(repository)


def get_solicitation_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> SolicitationService:
    return SolicitationService(SolicitationRepository(session))

from .config import (
    get_cloud_tasks_queue_path,
    get_triage_queue_backend,
    get_triage_worker_service_account,
    get_triage_worker_token,
    get_triage_worker_url,
)
from .services.triage import TriageWorkflowService
from .tasks.triage_queue import (
    CloudTasksTriageQueue,
    DisabledTriageQueue,
    TriageTaskQueue,
)


def get_triage_task_queue() -> TriageTaskQueue | None:
    backend = get_triage_queue_backend()
    if backend == "inline":
        return None
    if backend == "disabled":
        return DisabledTriageQueue()
    return CloudTasksTriageQueue(
        queue_path=get_cloud_tasks_queue_path(),
        worker_base_url=get_triage_worker_url(),
        service_account_email=get_triage_worker_service_account(),
    )


def get_triage_workflow_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    task_queue: Annotated[TriageTaskQueue | None, Depends(get_triage_task_queue)],
) -> TriageWorkflowService:
    return TriageWorkflowService(session, task_queue=task_queue)


async def verify_triage_worker_auth(
    authorization: Annotated[str | None, Header()] = None,
    x_triage_worker_token: Annotated[str | None, Header()] = None,
) -> None:
    """Aceita token interno compartilhado, OIDC do Cloud Tasks/Scheduler ou JWT de funcionário."""
    configured_token = get_triage_worker_token()
    if configured_token and x_triage_worker_token == configured_token:
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória para acionar a triagem.",
        )

    bearer_token = authorization.removeprefix("Bearer ").strip()
    if configured_token and bearer_token == configured_token:
        return

    # 1) Tenta validar como JWT de funcionário da aplicação
    session_maker = database.get_session_maker()
    try:
        async with session_maker() as session:
            user = await _build_auth_service(session).get_current_user(bearer_token)
            if user is not None:
                return
    except InvalidAccessTokenError:
        pass

    # 2) Tenta validar como token OIDC emitido pelo Google Cloud Tasks / Scheduler
    try:
        audience = get_triage_worker_url()
        claims = google_id_token.verify_oauth2_token(
            bearer_token,
            google_auth_requests.Request(),
            audience=audience,
        )
        expected_sa = os.getenv("TRIAGE_WORKER_SERVICE_ACCOUNT_EMAIL", "").strip()
        if expected_sa and claims.get("email") != expected_sa:
            raise ValueError("Service account mismatch.")
        return
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas para processamento de triagem.",
        ) from error