"""Single Gemini Decision Gate for RAG Local-First.

Enforces the strict rule: Gemini is positioned at the end of the pipeline.
In fast mode or for greetings/password/tool queries/extractive facts, requests stay 100% local.
In deep mode, complex or deep reasoning queries are forwarded to the configured external provider.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from backend.providers.llm.base import BaseLLMProvider
from backend.services.intent import Intent
from backend.services.rag.evidence_engine import EvidenceAnalysisResult
from backend.services.rag.tool_router import ToolRouteResult

logger = logging.getLogger("backend.services.rag.decision_gate")


@dataclass
class GateDecision:
    should_call_gemini: bool
    reason: str


def evaluate_gemini_gate(
    *,
    mode: str,
    intent: Intent,
    provider: BaseLLMProvider,
    tool_result: Optional[ToolRouteResult] = None,
    evidence_result: Optional[EvidenceAnalysisResult] = None,
    cooldown_active: bool = False,
) -> GateDecision:
    """Determine whether Gemini external LLM must be called."""

    # 1. Fast mode toggle -> always local
    if mode == "fast":
        return GateDecision(should_call_gemini=False, reason="fast_mode")

    # 2. Greeting or Password questions must be answered locally
    if intent in (Intent.GREETING, Intent.PASSWORD_QUESTION):
        return GateDecision(should_call_gemini=False, reason="intent_handled_locally")

    # 3. Provider unconfigured
    if not provider.is_configured or provider.name == "local":
        return GateDecision(should_call_gemini=False, reason="external_provider_not_configured")

    # 4. Provider 429 Cooldown active
    if cooldown_active:
        return GateDecision(should_call_gemini=False, reason="provider_cooldown_active")

    # 5. App Data / Tool routing answered query
    if tool_result and tool_result.handled:
        return GateDecision(
            should_call_gemini=False,
            reason=tool_result.metadata.get("routing_reason", "app_data_tool"),
        )

    # 6. High-confidence local evidence answers locally even in DEEP mode.
    # DEEP means "allow complex reasoning when needed", not "skip tools/RAG".
    if (
        evidence_result
        and evidence_result.can_answer_locally
        and not (mode == "deep" and evidence_result.answer_type == "no_evidence")
    ):
        return GateDecision(should_call_gemini=False, reason=evidence_result.routing_reason)

    # 7. Deep mode explicitly requested or complex reasoning
    return GateDecision(should_call_gemini=True, reason="deep_mode")
