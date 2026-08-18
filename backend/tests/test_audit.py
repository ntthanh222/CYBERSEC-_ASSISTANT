import json
import logging

from backend.core.audit import log_audit_event


def test_log_audit_event_emits_structured_json(caplog):
    caplog.set_level(logging.INFO, logger="backend.audit")
    log_audit_event(
        event_type="health_check",
        action="probe_dependencies",
        resource="system_health",
        result="success",
        metadata={"status": "healthy"},
    )
    assert any(r.name == "backend.audit" for r in caplog.records)


def test_system_health_call_emits_audit_event(client, caplog):
    caplog.set_level(logging.INFO, logger="backend.audit")
    client.get("/api/system/health")
    audit_records = [r for r in caplog.records if r.name == "backend.audit"]
    assert len(audit_records) == 1
    fields = audit_records[0].fields
    assert fields["event_type"] == "health_check"
    assert fields["resource"] == "system_health"
    assert fields["result"] in {"success", "failure"}


def test_audit_log_line_is_valid_json_via_formatter(client):
    from backend.core.logging import JSONFormatter

    record = logging.LogRecord(
        name="backend.audit",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="audit_event",
        args=(),
        exc_info=None,
    )
    record.fields = {"event_type": "health_check", "password": "hunter2"}
    formatted = JSONFormatter().format(record)
    payload = json.loads(formatted)
    assert payload["password"] == "***redacted***"
    assert payload["service"] == "backend"
