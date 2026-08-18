"""LLM provider contract.

Two invariants every implementation must uphold:

1. ``name`` is the value the API reports as ``provider``. It must describe what
   actually answered. A provider may never report a name it did not use - the
   blueprint is explicit that a rule-based or local answer must not be labelled
   as Gemini.
2. Failures are raised as :mod:`backend.core.exceptions` types, never as raw
   ``httpx`` or vendor exceptions, so the API surface stays stable and no
   upstream body text can leak into a response.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class LLMMessage:
    """One turn of conversation handed to a provider."""

    role: str
    content: str


@dataclass(frozen=True)
class LLMResult:
    """A provider's answer plus honest metadata about how it was produced."""

    content: str
    provider: str
    model: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """Abstract assistant backend."""

    #: Stable identifier reported to clients as ``provider``.
    name: str = "base"

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has everything it needs to run."""

    @abstractmethod
    async def generate(
        self,
        messages: Sequence[LLMMessage],
        *,
        system_prompt: str,
    ) -> LLMResult:
        """Produce an answer for ``messages``."""
