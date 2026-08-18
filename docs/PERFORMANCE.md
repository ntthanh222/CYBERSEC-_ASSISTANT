# Performance / Load Testing

## Tooling

k6, run via the official `grafana/k6` Docker image (no local install
needed). Script: [`tests/load/health_endpoints.js`](../tests/load/health_endpoints.js).

```bash
docker run --rm --network=host -e BASE_URL=http://localhost:8000 \
  -e K6_SCENARIO=smoke -v "$(pwd)/tests/load:/scripts" \
  grafana/k6 run /scripts/health_endpoints.js
# K6_SCENARIO: smoke | vus50 | vus100 | vus200
```

## Test design

Each virtual user loops: `GET /health` → `GET /api/system/health` →
`sleep(0.2s)`. Every stage profile ramps up, holds, and ramps down to zero
(finite duration, graceful stop) — no unbounded load.

Thresholds:

| Endpoint | Error rate | p95 latency |
|---|---|---|
| `/health` (dependency-free liveness) | < 1% | < 500ms |
| `/api/system/health` (real Postgres + Redis probes) | < 5% | < 1500ms |

`/api/system/health` gets a looser latency bar by design: it performs two
real synchronous network round trips (DB `SELECT 1`, Redis `PING`) on every
call, so it is inherently slower than a static liveness check — that is
correct behavior, not something to optimize away by faking the probe.

## Environment

Docker Desktop on Windows, single host, backend container capped at
`cpus: 1.0` / `mem_limit: 512m` (Docker hardening limits from this same
phase — see [docker-compose.yml](../docker-compose.yml)), 4-service stack
(frontend/backend/postgres/redis) all running locally alongside the test.

## Results (2026-07-29)

| Scenario | Duration | Peak VUs | Requests | Error rate | `/health` p95 | `/api/system/health` p95 | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| smoke | 25s | 2 | 340 | 0.00% | 8.6ms | 29.7ms | **PASS** |
| vus50 | 60s | 50 | 6,474 | 0.00% | 300ms | 783ms | **PASS** |
| vus100 | 80s | 100 | 15,088 | 0.00% | 262ms | 899ms | **PASS** |
| vus200 | 105s | 200 | 20,562 | 0.00% | 352ms | 2.55s | **THRESHOLD MISS** (latency only) |

## Finding: `/api/system/health` p95 exceeds threshold at 200 VU

At 200 concurrent VUs, `/api/system/health` p95 latency is 2.55s against a
1.5s threshold. **Zero requests failed or timed out** — every request
still eventually succeeded — so this is a capacity/latency finding, not a
correctness or stability bug.

**Root cause**: the backend container is deliberately capped to 1 CPU core
(Docker hardening in this same phase). At 200 concurrent requests, each
doing a real synchronous Postgres round trip + a real synchronous Redis
round trip, the single-core async event loop and the dependency connection
pools become the bottleneck — latency degrades gracefully rather than
requests failing outright, which is the expected shape of the degradation
given the resource cap.

**Not fixed in Phase 1.5** (out of scope — this phase hardens what exists,
it doesn't scale it): raising the CPU limit, adding connection pooling
tuning, or horizontal scaling are Phase 2+ concerns once real traffic
patterns are known. Recorded here as a known limit, not silently patched
around by loosening the k6 threshold to force a "pass".

**Quality Gate requirement #23 is "k6 smoke PASS"** — the smoke tier passed
cleanly with 0% errors and both endpoints well under their latency budgets.
The 50/100/200 VU tiers are informational capacity tests beyond that
requirement; running them and reporting the 200-VU finding honestly is more
useful than omitting them.

## Limitations of this benchmark

- Single-host, single-run: no statistical repeats, no isolated dedicated
  load-generation machine (k6 and the target stack share the same Docker
  Desktop host, so k6 itself consumes some of the same CPU/network it's
  measuring).
- No network latency (localhost only) — does not represent real
  client-to-server network conditions.
- Postgres/Redis have no artificial load of their own during the test
  (empty schema) — real Phase 2+ business tables under load would likely
  shift the bottleneck further.

Raw output: `.ai/PERFORMANCE_REPORT.md`.
