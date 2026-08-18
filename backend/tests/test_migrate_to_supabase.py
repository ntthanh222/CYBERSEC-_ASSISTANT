import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from backend.database.base import Base
from backend.database import models  # noqa: F401 - registers tables on Base.metadata
from backend.scripts.migrate_to_supabase import run


def _sqlite_url(tmp_path, name: str) -> str:
    path = tmp_path / name
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return f"sqlite:///{path}"


def _seed_source(url: str) -> uuid.UUID:
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    scan_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc).isoformat()
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversations (id, title, actor, user_id, created_at, updated_at) "
                "VALUES (:id, :title, :actor, :user_id, :created_at, :updated_at)"
            ),
            {
                "id": str(conv_id),
                "title": "Log4Shell triage",
                "actor": "anonymous",
                "user_id": str(user_id),
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO messages "
                "(id, conversation_id, role, content, provider, intent, metadata, created_at) "
                "VALUES (:id, :conversation_id, :role, :content, "
                ":provider, :intent, :metadata, :created_at)"
            ),
            {
                "id": str(msg_id),
                "conversation_id": str(conv_id),
                "role": "user",
                "content": "what is CVSS?",
                "provider": None,
                "intent": "definition",
                "metadata": None,
                "created_at": now,
            },
        )
        conn.execute(
            text(
                "INSERT INTO security_scan_history "
                "(id, scan_type, target, status, risk_score, severity, "
                "summary, details, actor, user_id, created_at) "
                "VALUES (:id, :scan_type, :target, :status, :risk_score, "
                ":severity, :summary, :details, :actor, :user_id, :created_at)"
            ),
            {
                "id": str(scan_id),
                "scan_type": "url_scan",
                "target": "https://example.com",
                "status": "completed",
                "risk_score": 10,
                "severity": "low",
                "summary": "clean",
                "details": None,
                "actor": "anonymous",
                "user_id": str(user_id),
                "created_at": now,
            },
        )
    engine.dispose()
    return conv_id


def _counts(url: str) -> dict:
    engine = create_engine(url)
    with engine.connect() as conn:
        result = {
            table: conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()  # noqa: S608
            for table in ("conversations", "messages", "security_scan_history")
        }
    engine.dispose()
    return result


def test_dry_run_copies_nothing(tmp_path):
    source_url = _sqlite_url(tmp_path, "source.db")
    target_url = _sqlite_url(tmp_path, "target.db")
    _seed_source(source_url)

    exit_code = run(source_url, target_url, dry_run=True)

    assert exit_code == 0
    assert _counts(target_url) == {"conversations": 0, "messages": 0, "security_scan_history": 0}


def test_execute_copies_all_rows_in_fk_safe_order(tmp_path):
    source_url = _sqlite_url(tmp_path, "source.db")
    target_url = _sqlite_url(tmp_path, "target.db")
    _seed_source(source_url)

    exit_code = run(source_url, target_url, dry_run=False)

    assert exit_code == 0
    assert _counts(target_url) == {"conversations": 1, "messages": 1, "security_scan_history": 1}


def test_execute_is_idempotent_on_rerun(tmp_path):
    source_url = _sqlite_url(tmp_path, "source.db")
    target_url = _sqlite_url(tmp_path, "target.db")
    _seed_source(source_url)

    run(source_url, target_url, dry_run=False)
    exit_code = run(source_url, target_url, dry_run=False)

    assert exit_code == 0
    assert _counts(target_url) == {"conversations": 1, "messages": 1, "security_scan_history": 1}


def test_source_is_never_modified(tmp_path):
    source_url = _sqlite_url(tmp_path, "source.db")
    target_url = _sqlite_url(tmp_path, "target.db")
    _seed_source(source_url)
    before = _counts(source_url)

    run(source_url, target_url, dry_run=False)

    assert _counts(source_url) == before


def test_does_not_overwrite_existing_target_row(tmp_path):
    source_url = _sqlite_url(tmp_path, "source.db")
    target_url = _sqlite_url(tmp_path, "target.db")
    conv_id = _seed_source(source_url)

    # Pre-seed the target with a conversation using the same id but a
    # different title - the tool must never overwrite it.
    engine = create_engine(target_url)
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversations (id, title, actor, user_id, created_at, updated_at) "
                "VALUES (:id, :title, :actor, :user_id, :created_at, :updated_at)"
            ),
            {
                "id": str(conv_id),
                "title": "PRE-EXISTING TITLE",
                "actor": "someone-else",
                "user_id": str(uuid.uuid4()),
                "created_at": now,
                "updated_at": now,
            },
        )
    engine.dispose()

    run(source_url, target_url, dry_run=False)

    engine = create_engine(target_url)
    with engine.connect() as conn:
        title = conn.execute(
            text("SELECT title FROM conversations WHERE id = :id"), {"id": str(conv_id)}
        ).scalar_one()
    engine.dispose()
    assert title == "PRE-EXISTING TITLE"
