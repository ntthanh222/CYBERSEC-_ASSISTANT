"""Unit tests for the Security News crawler's HTML-to-text cleanup.

CISA's advisory RSS ``description`` field is full HTML (headings, tables) -
see ``backend/services/security_news_crawler.py``'s ``_html_to_text``. The
UI renders ``summary`` as plain text, so raw markup reaching storage would
show up literally as ``&lt;h2&gt;`` to a reader instead of formatted content.
"""

from backend.services.security_news_crawler import _html_to_text


def test_strips_tags_and_unescapes_entities():
    raw = "<h2><strong>Advisory at a Glance</strong></h2> <p>Ransomware &amp; extortion.</p>"
    assert _html_to_text(raw) == "Advisory at a Glance Ransomware & extortion."


def test_table_markup_becomes_readable_text():
    raw = (
        "<table><tbody><tr><th>Title</th><td>Example Advisory</td></tr>"
        "<tr><th>Severity</th><td>Critical</td></tr></tbody></table>"
    )
    text = _html_to_text(raw)
    assert "<" not in text and ">" not in text
    assert "Title Example Advisory" in text
    assert "Severity Critical" in text


def test_plain_text_is_left_unchanged():
    assert _html_to_text("Already plain text, no markup here.") == (
        "Already plain text, no markup here."
    )


def test_empty_input_returns_empty_string():
    assert _html_to_text("") == ""
