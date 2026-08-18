"""Release-acceptance v0.2.7: real database unavailability/recovery drill.

Runs HTTP requests against a live backend container while genuinely pausing
and restarting its Postgres container via the Docker CLI (not a mock, not a
patched connection) - the same class of infrastructure-level failure
injection as `frontend/e2e/resilience.spec.ts`'s container-restart test from
Phase 2.7A, extended to cover the database specifically.

Usage::

    python -m backend.scripts.verify_db_resilience \\
        --base-url http://localhost:8102 \\
        --postgres-container release-acceptance-v027-postgres-1 \\
        --token <bearer-token-from-uat_mint_test_session>

This script only touches the Postgres container. It does not itself check
whether the *backend* container crashed/restarted during the drill - verify
that separately, e.g.::

    docker inspect <backend-container> --format 'RestartCount={{.RestartCount}}'
"""
import argparse
import json
import subprocess  # nosec B404 - operator-run local drill script, not a network-facing service
import sys
import time
import urllib.error
import urllib.request

MARKER_PREFIX = "release-acceptance-"


def _docker(*args: str) -> subprocess.CompletedProcess:
    # Fixed "docker" + a hardcoded/CLI-arg argument list, shell=False - the
    # safe invocation form; bandit's B603/B607 blacklist still flags any
    # subprocess call by pattern regardless of args being non-shell-parsed.
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False  # nosec B603 B607
    )


def _request(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
    timeout: float = 8.0,
):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    started = time.monotonic()
    try:
        # Fixed http(s) URL built from a --base-url the operator passes in,
        # never from network-sourced input - not the file://-scheme SSRF
        # class B310 warns about.
        with urllib.request.urlopen(  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            req, timeout=timeout
        ) as resp:
            elapsed = time.monotonic() - started
            return resp.status, resp.read(), elapsed
    except urllib.error.HTTPError as exc:
        elapsed = time.monotonic() - started
        return exc.code, exc.read(), elapsed
    except (urllib.error.URLError, TimeoutError) as exc:
        elapsed = time.monotonic() - started
        return None, str(exc).encode(), elapsed


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}{(' - ' + detail) if detail and not condition else ''}")
    return condition


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--postgres-container", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token
    pg = args.postgres_container
    failures = 0

    conversations_url = f"{base}/api/chatbot/conversations?page=1&page_size=5"

    # Baseline: DB up, request succeeds.
    status, _, _ = _request("GET", conversations_url, token)
    failures += not check(
        "baseline: conversations list succeeds with DB up", status == 200, f"status={status}"
    )

    # 1. Database unavailable mid-flight: STOP the container (not pause).
    # `docker pause` sends SIGSTOP, which freezes an in-flight query without
    # severing the TCP connection - on unpause the query resumes and can
    # still commit, which is a client-timeout-vs-server-still-working race,
    # not "the database was unavailable". `docker stop` actually tears the
    # connection down, the correct proxy for a real outage: the backend
    # must observe a hard connection failure, not a resumed one.
    _docker("stop", "-t", "1", pg)
    try:
        status, body, elapsed = _request(
            "POST",
            f"{base}/api/chatbot/conversations",
            token,
            {"title": f"{MARKER_PREFIX}db-unavailable-probe"},
            timeout=12.0,
        )
        failures += not check(
            "DB stopped: request fails fast/bounded, not hung forever",
            elapsed < 15.0,
            f"elapsed={elapsed:.1f}s",
        )
        failures += not check(
            "DB stopped: response is a server error, not a 2xx",
            status is None or status >= 500,
            f"status={status}",
        )
        body_text = body.decode(errors="replace") if isinstance(body, bytes) else str(body)
        no_leak = (
            "Traceback" not in body_text
            and "postgresql://" not in body_text
            and "psycopg" not in body_text.lower()
        )
        failures += not check("DB stopped: error body has no raw stack trace / DSN", no_leak)
    finally:
        _docker("start", pg)

    # Wait for Postgres to actually finish restarting before probing -
    # `docker start` returns as soon as the process launches, not once it's
    # accepting connections.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = _docker("exec", pg, "pg_isready", "-U", "cybersec")
        if result.returncode == 0:
            break
        time.sleep(1)

    # 2. Recovery: same request now succeeds again - proves the pool
    # recovers without a backend restart.
    status, body, _ = _request(
        "POST",
        f"{base}/api/chatbot/conversations",
        token,
        {"title": f"{MARKER_PREFIX}db-recovery-probe"},
        timeout=10.0,
    )
    failures += not check(
        "DB restarted: pool recovers, new request succeeds", status == 201, f"status={status}"
    )
    created_id = None
    if status == 201:
        try:
            created_id = json.loads(body)["id"]
        except (KeyError, ValueError):
            pass

    # 3. Concurrent requests immediately after recovery - pool must not be
    # exhausted/wedged by the paused-connection episode.
    concurrent_results = []
    for _ in range(8):
        s, _, _ = _request("GET", conversations_url, token, timeout=8.0)
        concurrent_results.append(s)
    failures += not check(
        "post-recovery: 8 sequential requests all succeed (no pool exhaustion)",
        all(s == 200 for s in concurrent_results),
        f"statuses={concurrent_results}",
    )

    # 4. Restart (not just stop/start) the DB container - proves recovery is
    # repeatable, not a one-time fluke of the first drill.
    _docker("restart", pg)
    deadline = time.monotonic() + 60
    recovered = False
    while time.monotonic() < deadline:
        s, _, _ = _request("GET", f"{base}/health", timeout=5.0)
        if s == 200:
            s2, _, _ = _request("GET", conversations_url, token, timeout=8.0)
            if s2 == 200:
                recovered = True
                break
        time.sleep(2)
    failures += not check("DB container restart: backend recovers within 60s", recovered)

    # 5. No orphan data: the failed create during the outage must not have
    # left a partial row (verified via a normal listing + title search;
    # anything from this run carries the release-acceptance marker so a
    # human/automated cleanup step can always find and remove it later).
    status, body, _ = _request(
        "GET", f"{base}/api/chatbot/conversations?page=1&page_size=50", token
    )
    titles = []
    if status == 200:
        try:
            titles = [c["title"] for c in json.loads(body).get("items", [])]
        except (KeyError, ValueError):
            pass
    failures += not check(
        "no orphan conversation from the failed paused-DB attempt",
        "release-acceptance-db-unavailable-probe" not in titles,
        f"titles={titles}",
    )

    # Cleanup: remove the one conversation this drill legitimately created.
    if created_id:
        _request("DELETE", f"{base}/api/chatbot/conversations/{created_id}", token)

    print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
