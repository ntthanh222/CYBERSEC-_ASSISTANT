"""URL/IP reputation providers - external verdicts, distinct from local heuristics."""
from backend.providers.reputation.virustotal import VirusTotalProvider

__all__ = ["VirusTotalProvider"]
