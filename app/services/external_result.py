"""Service client for retrieving cadastral results from an external API."""

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas import QueryRequest, QueryResponse


class ExternalServiceError(Exception):
    """Base error for external result service failures."""


class ExternalServiceUnavailableError(ExternalServiceError):
    """Raised when the external service cannot be reached or returns an error."""


class ExternalServiceTimeoutError(ExternalServiceError):
    """Raised when the external service request exceeds the configured timeout."""


class ExternalServiceInvalidResponseError(ExternalServiceError):
    """Raised when the external service response does not match the contract."""


async def fetch_external_result(payload: QueryRequest, settings: Settings) -> bool:
    """Send a cadastral check request to the configured external service.

    Args:
        payload: Validated cadastral check request from the API layer.
        settings: Runtime settings with external service URL and timeout.

    Returns:
        Boolean cadastral check result parsed from the external response.

    Raises:
        ExternalServiceTimeoutError: If the external request exceeds the
            configured timeout.
        ExternalServiceUnavailableError: If the external service cannot be
            reached.
        ExternalServiceInvalidResponseError: If the service returns an error
            status or a response that does not match the expected schema.
    """
    timeout = httpx.Timeout(settings.external_service_timeout)

    async with httpx.AsyncClient(
        base_url=settings.external_service_url,
        timeout=timeout,
    ) as client:
        try:
            response = await client.post("/result", json=payload.model_dump())
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ExternalServiceTimeoutError from exc
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceInvalidResponseError from exc
        except httpx.RequestError as exc:
            raise ExternalServiceUnavailableError from exc

    try:
        result = QueryResponse.model_validate(response.json())
    except (ValueError, ValidationError) as exc:
        raise ExternalServiceInvalidResponseError from exc

    return result.result
