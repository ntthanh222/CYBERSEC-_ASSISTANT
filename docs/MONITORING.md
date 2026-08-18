# Monitoring

## Metrics

`GET /metrics` on the backend exposes Prometheus-format metrics
(`backend/core/metrics.py`):

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `route`, `status_code` | Request volume by outcome |
| `http_request_duration_seconds` | Histogram | `method`, `route` | Latency distribution |
| `http_requests_in_progress` | Gauge | `method`, `route` | In-flight requests |
| `http_errors_total` | Counter | `method`, `route`, `error_type` | 5xx / unhandled exception count |
| `app_info` | Gauge (always 1) | `version`, `environment` | Build/version fingerprint |
| `dependency_probe_status` | Gauge (1/0) | `dependency` (backend/database/redis) | Latest health probe result |
| `dependency_probe_latency_ms` | Gauge | `dependency` | Latest health probe latency |

**Cardinality discipline**: every label is a route *template* (e.g.
`/api/system/health`, taken from Starlette's matched `route.path`) or a
fixed enum (method, status code, dependency name) — never a raw URL
containing an ID. No unbounded-cardinality labels exist.

**No secrets**: `/metrics` output was checked (`test_metrics.py::test_metrics_endpoint_never_leaks_secrets`)
to contain no `password`, `authorization`, or `secret` substrings.

## Scrape configuration

Phase 1.5 does not ship a Prometheus server container (kept out of scope
to avoid unnecessary complexity per this phase's own instructions — the
metrics endpoint is the requirement, not the full stack). To scrape
locally:

```yaml
# prometheus.yml (run separately, e.g. `docker run -p 9090:9090 -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus`)
scrape_configs:
  - job_name: cybersec-backend
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:8000"]
```

## Grafana

Not included — Prometheus is the required piece for this phase; a
dashboard can be added once real traffic/metrics exist to visualize.

## Health checks (separate from metrics)

- Docker healthchecks (`docker-compose.yml`): each of the 4 services has a
  real healthcheck (`pg_isready`, `redis-cli ping`, `curl /health`,
  `wget /health`), not just "container running."
- `GET /api/system/health`: human/UI-facing aggregated status — see
  [`docs/API.md`](API.md).
