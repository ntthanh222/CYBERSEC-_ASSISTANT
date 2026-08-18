"""Release-acceptance v0.2.7: continuous soak run against a disposable stack.

Real wall-clock duration only - never inflated. Mixes health checks,
authenticated conversation CRUD, RAG retrieval, and lightweight
security-tool requests against the live isolated backend. No paid AI
provider is called (none is configured in this environment - see the
release report's provider-fallback section). Concurrency is capped low by
design: this proves stability under sustained load, not maximum throughput,
and must never look like a DoS attempt.

Usage::

    python -m backend.scripts.verify_soak --base-url http://localhost:8102 \\
        --token <bearer-token> --minutes 30
"""
import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

MARKER_PREFIX = "release-acceptance-soak-"


def _request(
    method: str,
    url: str,
    token: str | None = None,
    body: dict | None = None,
    timeout: float = 10.0,
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
            body_bytes = resp.read()
            return resp.status, body_bytes, time.monotonic() - started
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), time.monotonic() - started
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # OSError also covers http.client.RemoteDisconnected/ConnectionReset
        # - a transient dropped keep-alive connection (e.g. the server
        # process restarting) must count as one failed request, not crash
        # the whole soak run. A real client tolerates this and keeps going.
        return None, str(exc).encode(), time.monotonic() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--minutes", type=float, default=30.0)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    token = args.token
    duration_target = args.minutes * 60
    start = time.monotonic()

    total = 0
    failures = 0
    latencies: list[float] = []
    created_ids: list[str] = []
    cycle = 0

    conversations_url = f"{base}/api/chatbot/conversations?page=1&page_size=10"

    print(f"Soak start: target {args.minutes} minutes against {base}")

    while time.monotonic() - start < duration_target:
        cycle += 1

        s, _, t = _request("GET", f"{base}/health", timeout=5.0)
        total += 1
        latencies.append(t)
        failures += s != 200

        s, body, t = _request(
            "POST",
            f"{base}/api/chatbot/conversations",
            token,
            {"title": f"{MARKER_PREFIX}{cycle}"},
            timeout=10.0,
        )
        total += 1
        latencies.append(t)
        failures += s != 201
        conv_id = None
        if s == 201:
            try:
                conv_id = json.loads(body)["id"]
                created_ids.append(conv_id)
            except (KeyError, ValueError):
                pass

        if conv_id:
            messages_url = f"{base}/api/chatbot/conversations/{conv_id}/messages?page=1&page_size=5"
            s, _, t = _request("GET", messages_url, token, timeout=10.0)
            total += 1
            latencies.append(t)
            failures += s != 200

        s, _, t = _request("GET", conversations_url, token, timeout=10.0)
        total += 1
        latencies.append(t)
        failures += s != 200

        # Deliberately infrequent: the endpoint is rate-limited (60/min) and
        # a 429 there is correct behavior, not a soak failure - hammering it
        # every cycle would just prove the limiter works, not stability.
        if cycle % 15 == 0:
            s, _, t = _request(
                "POST",
                f"{base}/api/tools/password-check",
                token,
                {"password": "hunter2-soak-probe-not-real"},
                timeout=8.0,
            )
            total += 1
            latencies.append(t)
            failures += s not in (200, 429)

        if cycle % 10 == 0:
            elapsed = time.monotonic() - start
            print(
                f"  cycle={cycle} elapsed={elapsed:.0f}s total={total} "
                f"failures={failures} p50={statistics.median(latencies):.3f}s"
            )

        time.sleep(1.0)  # deliberate pacing - stability proof, not a load/DoS test

    elapsed = time.monotonic() - start
    latencies.sort()
    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0.0

    print("\n--- Soak summary ---")
    print(f"duration_seconds={elapsed:.1f}")
    print(f"total_requests={total}")
    print(f"failures={failures}")
    print(f"error_rate={(failures / total * 100) if total else 0:.2f}%")
    print(f"p50_latency_s={p50:.3f}")
    print(f"p95_latency_s={p95:.3f}")
    print(f"conversations_created={len(created_ids)}")

    # Cleanup all soak-created conversations before reporting done.
    cleanup_failures = 0
    for conv_id in created_ids:
        delete_url = f"{base}/api/chatbot/conversations/{conv_id}"
        s, _, _ = _request("DELETE", delete_url, token, timeout=10.0)
        if s not in (200, 204):
            cleanup_failures += 1
    print(f"cleanup_failures={cleanup_failures}")

    print(json.dumps({
        "duration_seconds": round(elapsed, 1),
        "total_requests": total,
        "failures": failures,
        "p50_latency_s": round(p50, 3),
        "p95_latency_s": round(p95, 3),
        "conversations_created": len(created_ids),
        "cleanup_failures": cleanup_failures,
    }))

    ok = elapsed >= duration_target and failures == 0 and cleanup_failures == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
