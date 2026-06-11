import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.schemas import QueryRequest
from app.services import external_result
from app.services.external_result import (
    ExternalServiceInvalidResponseError,
    ExternalServiceTimeoutError,
    ExternalServiceUnavailableError,
    fetch_external_result,
)

REAL_ASYNC_CLIENT = httpx.AsyncClient


def make_settings() -> Settings:
    return Settings(
        database_url="postgresql://postgres:postgres@db:5432/test",
        external_service_url="http://external-service:8001",
        external_service_timeout=1.5,
    )


def make_payload() -> QueryRequest:
    return QueryRequest(
        cadastral_number="77:01:0004012:2054",
        latitude=55.7558,
        longitude=37.6173,
    )


def patch_async_client(
    monkeypatch, transport: httpx.MockTransport
) -> None:  # noqa: ANN001
    def client_factory(**kwargs) -> httpx.AsyncClient:  # noqa: ANN003
        return REAL_ASYNC_CLIENT(transport=transport, **kwargs)

    monkeypatch.setattr(external_result.httpx, "AsyncClient", client_factory)


def test_fetch_external_result_posts_payload_and_returns_boolean(
    monkeypatch,
) -> None:  # noqa: ANN001
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://external-service:8001/result"
        assert request.read() == (
            b'{"cadastral_number":"77:01:0004012:2054",'
            b'"latitude":55.7558,"longitude":37.6173}'
        )
        return httpx.Response(200, json={"result": True})

    patch_async_client(monkeypatch, httpx.MockTransport(handler))

    result = asyncio.run(fetch_external_result(make_payload(), make_settings()))

    assert result is True


def test_fetch_external_result_handles_unavailable_service(
    monkeypatch,
) -> None:  # noqa: ANN001
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    patch_async_client(monkeypatch, httpx.MockTransport(handler))

    with pytest.raises(ExternalServiceUnavailableError):
        asyncio.run(fetch_external_result(make_payload(), make_settings()))


def test_fetch_external_result_handles_timeout(monkeypatch) -> None:  # noqa: ANN001
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    patch_async_client(monkeypatch, httpx.MockTransport(handler))

    with pytest.raises(ExternalServiceTimeoutError):
        asyncio.run(fetch_external_result(make_payload(), make_settings()))


def test_fetch_external_result_handles_error_status(
    monkeypatch,
) -> None:  # noqa: ANN001
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "error"})

    patch_async_client(monkeypatch, httpx.MockTransport(handler))

    with pytest.raises(ExternalServiceInvalidResponseError):
        asyncio.run(fetch_external_result(make_payload(), make_settings()))


def test_fetch_external_result_handles_invalid_response(
    monkeypatch,
) -> None:  # noqa: ANN001
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    patch_async_client(monkeypatch, httpx.MockTransport(handler))

    with pytest.raises(ExternalServiceInvalidResponseError):
        asyncio.run(fetch_external_result(make_payload(), make_settings()))
