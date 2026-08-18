"""Google Gemini provider.

Talks to the Generative Language REST API directly over ``httpx`` rather than
pulling in a vendor SDK, which keeps the dependency surface (and therefore the
CVE surface) small.

Security and reliability rules enforced here:

* The API key is read from settings at call time and sent in the
  ``x-goog-api-key`` header - never in the URL query string, never logged, and
  never included in an exception message or in returned metadata.
* Every failure mode is translated into a :mod:`backend.core.exceptions` type.
  Upstream response bodies are never propagated to the client.
* Retries are bounded and only cover transport errors, timeouts and 5xx. A 4xx
  is a permanent answer and is never retried.
"""
import asyncio
import logging
from typing import Any, Final, Optional, Sequence

import httpx

from backend.config.settings import get_settings
from backend.core.exceptions import (
    ConfigurationMissingError,
    ProviderAuthenticationError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UpstreamMalformedError,
)
from backend.providers.llm.base import BaseLLMProvider, LLMMessage, LLMResult

logger = logging.getLogger("backend.providers.gemini")

DEFAULT_BASE_URL: Final = "https://generativelanguage.googleapis.com/v1beta"
REQUEST_TIMEOUT_SECONDS: Final = 20.0
MAX_ATTEMPTS: Final = 3
RETRY_BACKOFF_SECONDS: Final = 0.5


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.gemini_api_key
        self._model = model or settings.gemini_model
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    async def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        system_prompt: str,
    ) -> LLMResult:
        if not self.is_configured:
            # Guard against a programming error: the registry must not select
            # this provider without a key, and we refuse rather than pretend.
            raise ConfigurationMissingError(
                "The AI provider is not configured on this server."
            )

        payload = self._build_payload(messages, system_prompt=system_prompt)
        url = f"{self._base_url}/models/{self._model}:generateContent"
        response = await self._post_with_retries(url, payload)
        return LLMResult(
            content=self._extract_text(response),
            provider=self.name,
            model=self._model,
            metadata={"source": "gemini"},
        )

    @staticmethod
    def _build_payload(
        messages: Sequence[LLMMessage], *, system_prompt: str
    ) -> dict[str, Any]:
        contents = [
            {
                # Gemini only knows "user" and "model" roles.
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
            for message in messages
        ]
        return {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
        }

    async def _post_with_retries(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }
        last_error: Exception = ProviderUnavailableError()

        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = await client.post(url, json=payload, headers=headers)
                except httpx.TimeoutException:
                    last_error = ProviderTimeoutError()
                except httpx.HTTPError:
                    # Covers connection/DNS/protocol errors. The exception text
                    # is not propagated: it can contain the full request URL.
                    last_error = ProviderUnavailableError()
                else:
                    if response.status_code == 429:
                        raise ProviderRateLimitedError()
                    if 400 <= response.status_code < 500:
                        logger.warning(
                            "gemini_client_error",
                            extra={"fields": {"status_code": response.status_code}},
                        )
                        if _is_invalid_api_key_response(response):
                            raise ProviderAuthenticationError(
                                "The Gemini API rejected the configured API key."
                            )
                        raise ProviderUnavailableError(
                            "The AI provider rejected the request."
                        )
                    if response.status_code >= 500:
                        last_error = ProviderUnavailableError()
                    else:
                        return self._parse_json(response)

                if attempt < self._max_attempts:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        logger.warning(
            "gemini_request_failed",
            extra={"fields": {"attempts": self._max_attempts, "error": type(last_error).__name__}},
        )
        raise last_error

    async def list_models(self) -> list[str]:
        """Dynamically discover which models this key can currently use -
        never rely on a stale hardcoded model name being right forever.
        Returns bare model ids (``gemini-2.5-flash``, not ``models/
        gemini-2.5-flash``). Raises the same categorized errors as
        :meth:`generate` on failure - a caller that only wants a best-effort
        check should catch broadly."""
        if not self.is_configured:
            raise ConfigurationMissingError("The AI provider is not configured on this server.")

        headers = {"x-goog-api-key": self._api_key}
        url = f"{self._base_url}/models"
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds, transport=self._transport
        ) as client:
            try:
                response = await client.get(url, headers=headers)
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError() from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailableError() from exc

        if response.status_code == 429:
            raise ProviderRateLimitedError()
        if 400 <= response.status_code < 500:
            if _is_invalid_api_key_response(response):
                raise ProviderAuthenticationError(
                    "The Gemini API rejected the configured API key."
                )
            raise ProviderUnavailableError("The AI provider rejected the request.")
        if response.status_code >= 500:
            raise ProviderUnavailableError()

        data = self._parse_json(response)
        models = data.get("models")
        if not isinstance(models, list):
            raise UpstreamMalformedError()
        return [
            str(m["name"]).removeprefix("models/")
            for m in models
            if isinstance(m, dict) and "name" in m
        ]

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamMalformedError() from exc
        if not isinstance(data, dict):
            raise UpstreamMalformedError()
        return data

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise UpstreamMalformedError() from exc
        if not text.strip():
            raise UpstreamMalformedError()
        return text


def _is_invalid_api_key_response(response: httpx.Response) -> bool:
    """True only for Gemini's specific, documented invalid-key shape: HTTP
    400, ``error.status == "INVALID_ARGUMENT"``, and an ``ErrorInfo`` detail
    with ``reason == "API_KEY_INVALID"`` - verified directly against the
    live API with a deliberately malformed key. Matching on the structured
    ``reason`` enum (not a substring of the human-readable message, which
    Google can freely reword) is what keeps this from misclassifying an
    unrelated 400 as an authentication failure."""
    try:
        body = response.json()
    except ValueError:
        return False
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict) or error.get("status") != "INVALID_ARGUMENT":
        return False
    details = error.get("details")
    if not isinstance(details, list):
        return False
    return any(isinstance(d, dict) and d.get("reason") == "API_KEY_INVALID" for d in details)
