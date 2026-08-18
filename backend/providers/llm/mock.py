"""Deterministic provider used by the test suite.

Never selected by :func:`backend.providers.llm.registry.get_llm_provider`; a
test injects it explicitly. It can be configured to fail so that the
orchestrator's error mapping is exercised without touching the network.
"""
from typing import Optional, Sequence

from backend.providers.llm.base import BaseLLMProvider, LLMMessage, LLMResult


class MockProvider(BaseLLMProvider):
    name = "mock"

    def __init__(
        self,
        *,
        reply: str = "Mock assistant reply.",
        configured: bool = True,
        raises: Optional[Exception] = None,
    ) -> None:
        self._reply = reply
        self._configured = configured
        self._raises = raises
        self.calls: list[Sequence[LLMMessage]] = []

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        system_prompt: str,
    ) -> LLMResult:
        self.calls.append(list(messages))
        if self._raises is not None:
            raise self._raises
        return LLMResult(
            content=self._reply,
            provider=self.name,
            model="mock-1",
            metadata={"source": "mock"},
        )
