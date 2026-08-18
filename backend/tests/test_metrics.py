def test_metrics_endpoint_exposes_prometheus_format(client):
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "app_info" in body


def test_metrics_reflect_system_health_probe(client):
    client.get("/api/system/health")
    response = client.get("/metrics")
    body = response.text
    assert "dependency_probe_status" in body
    assert 'dependency="database"' in body
    assert 'dependency="redis"' in body


def test_metrics_endpoint_never_leaks_secrets(api_client):
    # Phase 2 legitimately adds a metric named "password_checks_total" (its
    # label is one of four fixed strength buckets - never a password value),
    # so this can no longer ban the literal substring "password". What it
    # must still guarantee is that no actual secret VALUE ever reaches
    # /metrics, which is exercised here with a real, distinctive password.
    secret_password = "Tr0ub4dor&3-MetricsLeakCanary-DoNotExpose!"
    api_client.post("/api/tools/password-check", json={"password": secret_password})

    response = api_client.get("/metrics")
    body = response.text
    assert secret_password not in body
    assert secret_password.lower() not in body.lower()

    lowered = body.lower()
    assert "authorization" not in lowered
    assert "secret" not in lowered
    # The metric name/label is allowed; only the fixed bucket vocabulary may
    # follow it, never an arbitrary value.
    assert "password_checks_total" in body
    assert 'strength="very_strong"' in body
