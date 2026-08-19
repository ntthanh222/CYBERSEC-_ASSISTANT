"""Unit tests for backend.services.finding_fingerprint - target
normalization and fingerprint stability (Task 3).

Fingerprint stability across textually-different-but-logically-identical
targets is the entire point of this module: a normalization bug here would
silently make a rescan see "STILL_OPEN" findings as brand new ones."""
import uuid

from backend.services.finding_fingerprint import compute_fingerprint, normalize_target


# ─── normalize_target ───────────────────────────────────────────────────────


def test_lowercases_scheme_and_host():
    assert normalize_target("HTTPS://Example.COM/path") == "https://example.com/path"


def test_strips_default_https_port():
    assert normalize_target("https://example.com:443/path") == "https://example.com/path"


def test_strips_default_http_port():
    assert normalize_target("http://example.com:80/path") == "http://example.com/path"


def test_preserves_non_default_port():
    assert normalize_target("https://example.com:8443/path") == "https://example.com:8443/path"


def test_strips_trailing_slash():
    assert normalize_target("https://example.com/path/") == "https://example.com/path"


def test_bare_root_and_trailing_slash_root_are_identical():
    assert normalize_target("https://example.com") == normalize_target("https://example.com/")


def test_strips_query_string():
    assert normalize_target("https://example.com/path?x=1&y=2") == "https://example.com/path"


def test_strips_fragment():
    assert normalize_target("https://example.com/path#section") == "https://example.com/path"


def test_full_example_from_brief():
    assert (
        normalize_target("HTTPS://Example.com:443/path/?x=1#frag")
        == "https://example.com/path"
    )


def test_drops_credentials():
    assert normalize_target("https://user:pass@example.com/path") == "https://example.com/path"


def test_multiple_trailing_slashes_collapse():
    assert normalize_target("https://example.com/path//") == "https://example.com/path"


def test_no_scheme_falls_back_to_lowercased_stripped_string():
    # url_scanner always supplies a scheme in practice, but this must not
    # raise on an already-unusual target.
    assert normalize_target("EXAMPLE.COM/PATH/") == "example.com/path"


# ─── compute_fingerprint stability ──────────────────────────────────────────


def test_same_logical_target_in_different_textual_forms_has_the_same_fingerprint():
    project_id = uuid.uuid4()
    a = compute_fingerprint(
        project_id=project_id,
        rule_id="no_https",
        category="no_https",
        target="HTTPS://Example.com:443/path/?x=1#frag",
    )
    b = compute_fingerprint(
        project_id=project_id,
        rule_id="no_https",
        category="no_https",
        target="https://example.com/path",
    )
    assert a == b


def test_different_rule_id_produces_different_fingerprint():
    project_id = uuid.uuid4()
    a = compute_fingerprint(
        project_id=project_id, rule_id="no_https", category="c", target="https://example.com/"
    )
    b = compute_fingerprint(
        project_id=project_id, rule_id="long_url", category="c", target="https://example.com/"
    )
    assert a != b


def test_different_category_produces_different_fingerprint():
    project_id = uuid.uuid4()
    a = compute_fingerprint(
        project_id=project_id, rule_id="r", category="cat1", target="https://example.com/"
    )
    b = compute_fingerprint(
        project_id=project_id, rule_id="r", category="cat2", target="https://example.com/"
    )
    assert a != b


def test_different_project_id_produces_different_fingerprint():
    a = compute_fingerprint(
        project_id=uuid.uuid4(), rule_id="r", category="c", target="https://example.com/"
    )
    b = compute_fingerprint(
        project_id=uuid.uuid4(), rule_id="r", category="c", target="https://example.com/"
    )
    assert a != b


def test_different_normalized_target_produces_different_fingerprint():
    project_id = uuid.uuid4()
    a = compute_fingerprint(
        project_id=project_id, rule_id="r", category="c", target="https://example.com/a"
    )
    b = compute_fingerprint(
        project_id=project_id, rule_id="r", category="c", target="https://example.com/b"
    )
    assert a != b


def test_fingerprint_is_a_64_char_hex_sha256_digest():
    fingerprint = compute_fingerprint(
        project_id=uuid.uuid4(), rule_id="r", category="c", target="https://example.com/"
    )
    assert len(fingerprint) == 64
    int(fingerprint, 16)  # raises ValueError if not valid hex
