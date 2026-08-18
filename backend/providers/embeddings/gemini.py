"""Google Gemini embedding provider - the optional, opt-in cloud path.

Only ever selected when both ``EMBEDDING_PROVIDER=gemini`` *and*
``GEMINI_API_KEY`` are set (:attr:`backend.config.settings.Settings.
embedding_cloud_configured`); :mod:`backend.providers.embeddings.local` is
the default. This exists so an operator can deliberately trade the local
model for a managed one, not because it is used implicitly - see
:mod:`backend.providers.embeddings.registry`.

Talks to the Generative Language REST API directly over ``httpx``, mirroring
:mod:`backend.providers.llm.gemini`'s security/reliability rules: the API key
is sent only in the ``x-goog-api-key`` header, never logged or echoed; every
failure is translated into a :mod:`backend.core.exceptions` type; a 4xx is
never retried.
"""
import asyncio
import logging
from typing import Any, Dict, Final, List, Optional, Sequence

import httpx

from backend.config.settings import get_settings
from backend.core.exceptions import (
    ConfigurationMissingError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)
from backend.providers.embeddings.base import BaseEmbeddingProvider

logger = logging.getLogger("backend.providers.embeddings.gemini")

DEFAULT_BASE_URL: Final = "https://generativelanguage.googleapis.com/v1beta"
REQUEST_TIMEOUT_SECONDS: Final = 20.0
MAX_ATTEMPTS: Final = 3
RETRY_BACKOFF_SECONDS: Final = 0.5


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
        base_url: str = DEFAULT_BASE_URL,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self._model = model or settings.gemini_embedding_model
        self._dimension = dimension or settings.embedding_dimension
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        if not self.is_configured:
            raise ConfigurationMissingError(
                "The cloud embedding provider is not configured on this server."
            )
        return [await self._embed_one(text) for text in texts]

    async def _embed_one(self, text: str) -> List[float]:
        url = f"{self._base_url}/models/{self._model}:embedContent"
        payload = {"content": {"parts": [{"text": text}]}}
        data = await self._post_with_retries(url, payload)
        try:
            values = data["embedding"]["values"]
        except (KeyError, TypeError) as exc:
            raise UpstreamMalformedError() from exc
        if not isinstance(values, list) or not values:
            raise UpstreamMalformedError()
        return [float(value) for value in values]

    async def _post_with_retries(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"x-goog-api-key": self._api_key, "content-type": "application/json"}
        last_error: Exception = ProviderUnavailableError()

        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = await client.post(url, json=payload, headers=headers)
                except httpx.TimeoutException:
                    last_error = ProviderTimeoutError()
                except httpx.HTTPError:
                    last_error = ProviderUnavailableError()
                else:
                    if response.status_code == 429:
                        raise ProviderRateLimitedError()
                    if 400 <= response.status_code < 500:
                        logger.warning(
                            "gemini_embedding_client_error",
                            extra={"fields": {"status_code": response.status_code}},
                        )
                        raise ProviderUnavailableError(
                            "The embedding provider rejected the request."
                        )
                    if response.status_code >= 500:
                        last_error = ProviderUnavailableError()
                    else:
                        return self._parse_json(response)

                if attempt < self._max_attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        logger.warning(
            "gemini_embedding_request_failed",
            extra={"fields": {"attempts": self._max_attempts, "error": type(last_error).__name__}},
        )
        raise last_error

    @staticmethod
    def _parse_json(response: httpx.Response) -> Dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamMalformedError() from exc
        if not isinstance(data, dict):
            raise UpstreamMalformedError()
        return data
