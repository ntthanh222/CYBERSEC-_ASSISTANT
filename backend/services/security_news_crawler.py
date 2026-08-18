"""Small, allowlisted Security News crawler for public RSS feeds."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import defusedxml.ElementTree as ET
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.audit import log_audit_event
from backend.repositories.security_news import SecurityNewsRepository


class _TagStripper(HTMLParser):
    """Collects only the text content of an HTML fragment, dropping tags.

    Every tag boundary also appends a space: source markup like
    ``<th>Title</th><td>Example</td>`` has no whitespace between the tags
    themselves, so without this a naive strip-and-join would concatenate
    adjacent cells into one run-on word (``TitleExample``). The extra
    spaces this introduces around genuine word boundaries are harmless -
    collapsed right back down by the whitespace cleanup in ``_html_to_text``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        self._chunks.append(" ")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _html_to_text(raw: str) -> str:
    """Advisory feeds (CISA in particular) put full HTML - headings, tables -
    in the RSS ``description``. The UI renders ``summary`` as plain text, so
    stripped-down readable text belongs here, not raw markup a reader would
    otherwise see literally as ``&lt;h2&gt;`` tags."""
    stripper = _TagStripper()
    stripper.feed(raw)
    text = unescape(stripper.text())
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


@dataclass(frozen=True)
class NewsSource:
    name: str
    url: str
    enabled: bool = True


NEWS_SOURCES = [
    NewsSource("CISA Alerts", "https://www.cisa.gov/cybersecurity-advisories/all.xml"),
    NewsSource("NVD Recent CVEs", "https://nvd.nist.gov/feeds/xml/cve/misc/nvd-rss.xml"),
]

_ALLOWED_HOSTS = {"www.cisa.gov", "nvd.nist.gov"}
_LAST_RUN: dict[str, Any] = {
    "last_run": None,
    "articles_collected": 0,
    "failed_items": 0,
    "last_result": "not_started",
    "errors": [],
    "sources": [],
}


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _text(node: Any, name: str) -> str:
    found = node.find(name)
    return (found.text or "").strip() if found is not None else ""


def _parse_items(source: NewsSource, raw: str) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    items = root.findall(".//item")[:20]
    parsed: list[dict[str, Any]] = []
    for item in items:
        title = _text(item, "title")
        link = _text(item, "link")
        summary = _html_to_text(_text(item, "description")) or title
        if not title or not link:
            continue
        parsed.append(
            {
                "title": title[:300],
                "url": link[:1000],
                "source": source.name,
                "summary": summary[:2000],
                "ai_summary": "",
                "published_at": _parse_dt(_text(item, "pubDate")),
                "category": "security-news",
                "related_cves": [],
                "bookmarked": False,
                "read": False,
            }
        )
    return parsed


async def run_security_news_crawler(
    session: AsyncSession, *, user_id: UUID, actor: str | None
) -> dict[str, Any]:
    repo = SecurityNewsRepository(session)
    collected = 0
    failed = 0
    source_statuses: list[dict[str, Any]] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for source in NEWS_SOURCES:
            host = urlparse(source.url).hostname or ""
            if not source.enabled or host not in _ALLOWED_HOSTS:
                source_statuses.append(
                    {
                        "source": source.name,
                        "enabled": source.enabled,
                        "last_result": "skipped",
                    }
                )
                continue
            try:
                response = await client.get(
                    source.url,
                    headers={"User-Agent": "CyberSecAssistantDemoCrawler/1.0"},
                )
                response.raise_for_status()
                created_for_source = 0
                for item in _parse_items(source, response.text):
                    if await repo.get_by_url(item["url"]):
                        continue
                    await repo.create(user_id=user_id, **item)
                    created_for_source += 1
                collected += created_for_source
                source_statuses.append(
                    {
                        "source": source.name,
                        "enabled": True,
                        "last_result": "ok",
                        "articles_collected": created_for_source,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - one broken source must not break the crawler
                failed += 1
                message = f"{source.name}: {type(exc).__name__}"
                errors.append(message)
                source_statuses.append(
                    {
                        "source": source.name,
                        "enabled": True,
                        "last_result": "failed",
                        "error": message,
                    }
                )

    await session.commit()
    result = "ok" if failed == 0 else "partial"
    _LAST_RUN.update(
        {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "articles_collected": collected,
            "failed_items": failed,
            "last_result": result,
            "errors": errors,
            "sources": source_statuses,
        }
    )
    log_audit_event(
        event_type="admin",
        action="security_news_crawler_run",
        resource="security_news:crawler",
        result=result,
        actor=actor,
        metadata={"articles_collected": collected, "failed_items": failed},
    )
    return crawler_status()


def crawler_status() -> dict[str, Any]:
    sources = _LAST_RUN.get("sources") or [
        {
            "source": source.name,
            "enabled": source.enabled,
            "url": source.url,
            "last_result": "not_started",
            "articles_collected": 0,
        }
        for source in NEWS_SOURCES
    ]
    return {
        "status": "idle",
        "last_run": _LAST_RUN["last_run"],
        "next_run": None,
        "articles_collected": _LAST_RUN["articles_collected"],
        "failed_items": _LAST_RUN["failed_items"],
        "last_result": _LAST_RUN["last_result"],
        "errors": _LAST_RUN["errors"],
        "sources": sources,
    }
