from threading import Lock
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from google.cloud.storage import Client
from sqlalchemy.ext.asyncio import AsyncSession
from .repositories.lot_draft import LotDraftRepository
from .services.lot_draft import LotDraftService
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
from .repositories.lot import LotRepository
from .repositories.order import OrderRepository
from .repositories.order_draft import OrderDraftRepository
from .repositories.producer import ProducerRepository
from .repositories.product import ProductRepository
from .repositories.solicitation import SolicitationRepository
from .repositories.user import UserRepository
from .services.auth import AuthService, InvalidAccessTokenError
from .services.chat import ChatService
from .services.document import DocumentService
from .services.lot import LotService
from .services.order import OrderService
from .services.order_draft import OrderDraftService
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
    session: Annotated[
        AsyncSession,
        Depends(get_db, scope="function"),
    ],
) -> OrderService:
    return OrderService(
        repository=OrderRepository(session),
        product_repository=ProductRepository(session),
    )


def get_lot_service(
    session: Annotated[
        AsyncSession,
        Depends(get_db, scope="function"),
    ],
) -> LotService:
    return LotService(
        repository=LotRepository(session),
        order_repository=OrderRepository(session),
        producer_repository=ProducerRepository(session),
    )


def get_solicitation_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> SolicitationService:
    return SolicitationService(SolicitationRepository(session))

def get_lot_draft_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
    lot_service: Annotated[LotService, Depends(get_lot_service)],
) -> LotDraftService:
    return LotDraftService(
        draft_repository=LotDraftRepository(session),
        chat_repository=ChatRepository(session),
        order_repository=OrderRepository(session),
        lot_service=lot_service,
    )

def get_order_draft_service(
    session: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> OrderDraftService:
    return OrderDraftService(
        repository=OrderDraftRepository(session),
        order_service=OrderService(
            OrderRepository(session),
            ProductRepository(session),
        ),
        chat_repository=ChatRepository(session),
        solicitation_repository=SolicitationRepository(session),
    )
