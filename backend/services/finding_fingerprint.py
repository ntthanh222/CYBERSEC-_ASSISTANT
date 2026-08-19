"""Target normalization + fingerprint computation (Task 3).

Isolated on purpose from ``backend.services.finding``/``scan_orchestrator``
so ``normalize_target`` can be exhaustively unit tested on its own (see
``backend/tests/test_finding_fingerprint.py``) - fingerprint *stability*
across textually-different-but-logically-identical targets is the entire
point of this module, and a normalization bug here would silently break
rescan matching (a "STILL_OPEN" finding would instead look like a brand new
one on every scan).

The fingerprint formula's SHAPE is unchanged from Task 2
(``sha256(f"{project_id}:{rule_id}:{category}:{target}")``) - only its
``target`` input is now normalized first. Changing the shape itself would
silently invalidate every Finding's fingerprint already computed in Task 2's
tests/data, which is explicitly out of scope here.
"""
from __future__ import annotations

import hashlib
import uuid
from urllib.parse import urlsplit, urlunsplit

#: Ports that are implied by their scheme and therefore carry no
#: fingerprinting-relevant information - "https://x:443/" and "https://x/"
#: are the same target.
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_target(target: str) -> str:
    """Normalize a scan target URL so textually-different forms of the same
    logical target fingerprint identically.

    Applied, in order:
    - lowercase the scheme and host (``urlsplit().hostname`` already
      lowercases the host; the scheme is lowercased explicitly since
      ``urlsplit`` does not normalize it on every Python version),
    - strip the port when it is the scheme's default (80 for http, 443 for
      https) - an explicit non-default port is preserved,
    - strip a trailing slash from the path (``/path/`` -> ``/path``; a bare
      ``/`` collapses to ``""`` so ``https://x`` and ``https://x/`` match),
    - drop the query string and fragment entirely - they carry no identity
      for fingerprinting purposes and their presence/order/casing must never
      cause two scans of "the same" target to produce different fingerprints,
    - credentials (``user:pass@``), if present in the input, are dropped as
      a side effect of rebuilding the netloc from ``hostname``/``port`` only.

    A target with no recognizable scheme (rare - the URL scanner requires
    one) is lowercased and trailing-slash-stripped as a best-effort fallback
    rather than raising, so a malformed-but-still-hashable target never
    crashes a scan.
    """
    target = target.strip()
    parts = urlsplit(target)

    if not parts.scheme or parts.hostname is None:
        # No recognizable scheme://host - fingerprint the lowercased,
        # trailing-slash-stripped raw string rather than raising, so this
        # never crashes a scan over an already-unusual target.
        lowered = target.lower()
        if len(lowered) > 1 and lowered.endswith("/"):
            lowered = lowered.rstrip("/")
        return lowered

    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower()
    port = parts.port
    if port is not None and _DEFAULT_PORTS.get(scheme) == port:
        port = None
    netloc = hostname if port is None else f"{hostname}:{port}"

    path = parts.path.rstrip("/")

    # Query string and fragment are intentionally dropped (empty strings).
    return urlunsplit((scheme, netloc, path, "", ""))


def compute_fingerprint(*, project_id: uuid.UUID, rule_id: str, category: str, target: str) -> str:
    """``sha256(f"{project_id}:{rule_id}:{category}:{normalize_target(target)}")``.

    Same formula shape as Task 2's ``backend.services.finding.compute_fingerprint``
    (now a thin wrapper around this function) - only ``target`` is normalized
    first.
    """
    normalized = normalize_target(target)
    raw = f"{project_id}:{rule_id}:{category}:{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
