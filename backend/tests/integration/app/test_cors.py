import importlib
from collections.abc import AsyncIterator
from io import BytesIO
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

import api.app
from api.dependencies import get_current_user, get_document_service
from api.services.document import DocumentService


@pytest_asyncio.fixture
async def client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    app_module = importlib.reload(api.app)
    transport = httpx.ASGITransport(app=app_module.app, raise_app_exceptions=False)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_cors_preflight_allows_configured_origin(
    client: httpx.AsyncClient,
) -> None:
    response = await client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )
    assert response.headers["access-control-allow-methods"] == "GET, POST, PUT, PATCH, DELETE"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "Authorization" in response.headers["access-control-allow-headers"]
    assert "Content-Type" in response.headers["access-control-allow-headers"]


@pytest.mark.asyncio
async def test_cors_preflight_rejects_unconfigured_origin(
    client: httpx.AsyncClient,
) -> None:
    response = await client.options(
        "/auth/login",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_cors_allows_document_delete_preflight(client: httpx.AsyncClient) -> None:
    origin = "http://localhost:5173"
    response = await client.options(
        f"/documents/{uuid4()}",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "DELETE" in response.headers["access-control-allow-methods"].split(", ")
    assert "Authorization" in response.headers["access-control-allow-headers"]


@pytest.mark.asyncio
async def test_cors_exposes_content_disposition_for_document_download(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = Mock(spec=DocumentService)
    service.prepare_document_read.return_value = (
        "certificado.pdf", lambda: BytesIO(b"content")
    )
    overrides = api.app.fastapi_app.dependency_overrides
    monkeypatch.setitem(overrides, get_current_user, lambda: object())
    monkeypatch.setitem(overrides, get_document_service, lambda: service)
    origin = "http://localhost:5173"

    response = await client.get(f"/documents/{uuid4()}/download", headers={"Origin": origin})

    assert response.status_code == 200
    assert "content-disposition" in response.headers
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-expose-headers"] == "Content-Disposition"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("origin", "expected_origin"),
    [
        ("http://localhost:5173", "http://localhost:5173"),
        ("https://example.com", None),
    ],
)
async def test_cors_on_unhandled_document_error(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    expected_origin: str | None,
) -> None:
    service = Mock(spec=DocumentService)
    open_reader = Mock(side_effect=OSError("storage unavailable"))
    service.prepare_document_read.return_value = ("certificado.pdf", open_reader)
    overrides = api.app.fastapi_app.dependency_overrides
    monkeypatch.setitem(overrides, get_current_user, lambda: object())
    monkeypatch.setitem(overrides, get_document_service, lambda: service)

    response = await client.get(f"/documents/{uuid4()}/download", headers={"Origin": origin})

    open_reader.assert_called_once_with()
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == expected_origin
