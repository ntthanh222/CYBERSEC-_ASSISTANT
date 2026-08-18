# Chatbot + Toolkit Validation Against Supabase (Phase 2.5A)

This checklist has now been run for real against a live Supabase project
(`vrspachjdttxdkigcuzv`, `ap-northeast-2`), not just Docker Postgres. All
test data was prefixed `supabase-validation-` and deleted afterward; the
project ended the run with 0 conversations and 0 scan-history rows.

Setup used for this run: `DATABASE_URL` = Session Pooler,
`DATABASE_MIGRATION_URL` = Session Pooler as well (the project's Direct
connection host resolves IPv6-only and this Docker network has no IPv6
route - `Name does not resolve`, confirmed live - exactly the fallback
`docs/SUPABASE_SETUP.md` documents). `APP_ENV=staging`,
`DATABASE_SSL_MODE=require`. Backend reached via `docker compose run`/
`up` with the container's default entrypoint (`alembic upgrade head` then
`uvicorn`), host port temporarily remapped to avoid colliding with an
unrelated already-running stack on the host - reverted afterward.

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Connection | PASS | `db_preflight.py --target runtime --expect-staging` exit 0, host confirmed remote & staging |
| 2 | SSL | PASS | `sslmode configured: True` |
| 3 | Migration to 0003 | PASS | `alembic current` before: unstamped; `alembic history`: `<base>->0001->0002->0003 (head)`, no `0004`; `alembic upgrade head` succeeded; `alembic current` after: `0003 (head)` |
| 4 | Create conversation | PASS | `POST /api/chatbot/chat` (no `conversation_id`) returns `200`, new UUID `conversation_id` |
| 5 | Send user message | PASS | Both `user` and `assistant` messages persisted; confirmed via `GET .../messages` (4 rows across 2 turns) |
| 6 | List conversations | PASS | Paginated envelope `{items, total, page, page_size}` correct |
| 7 | Conversation detail | PASS | `GET /api/chatbot/conversations/{id}` returns `200` |
| 8 | Delete conversation | PASS | `DELETE` -> `204`, then `GET` on the same id and its `/messages` both -> `404` |
| 9 | Persistence after restart | PASS | `docker compose restart backend`, re-fetched the same conversation's 4 messages - all present, content unchanged |
| 10 | No orphaned messages | PASS | See #11 - the forced-failure run produced 0 conversations, not just 0 orphaned messages |
| 11 | Transaction rollback on AI provider error | PASS | `GEMINI_API_KEY` temporarily set to an invalid test value (never a real key) to force a genuine provider rejection (`502 provider_unavailable`) in `mode=deep`; conversation list afterward: `total: 0`. The whole session rolled back, not just the trailing message - `chat()`'s `add_message` for the user turn is `flush()`ed but never `commit()`ed before the provider call, and `get_db` rolls back on exception. Key restored to empty and the container recreated afterward. |
| 12 | Pagination | PASS | 3 conversations, `page_size=2` -> page 1: 2 items, page 2: 1 item, `total: 3` |
| 13 | Timestamps | PASS | All `created_at`/`updated_at` end in `+00:00` |
| 14 | Scan history persists | PASS | `POST /api/tools/url-scan` against a `.example.test` host (expected DNS failure, blocked by the SSRF guard) still wrote a `failed` history row |
| 15 | Scan history CRUD | PASS | List, detail, delete -> `204`, then `404` |
| 16 | CVE cache still Redis, unaffected by DB change | not re-run this session | Unaffected by any change made (CVE lookup uses the existing Redis cache path, untouched) |
| 17 | Password never persisted | not re-run this session | No password-check calls were made in this validation run; behavior is unchanged from Phase 2 and covered by existing tests |
| 18 | Concurrent requests | PASS | 8 parallel `POST /api/chatbot/chat` calls, all `200`, 8 distinct conversation UUIDs (no PK collisions), no pool-exhaustion errors against `pool_size=5, max_overflow=5` |

## Bugs found and fixed during this run

Neither bug was Supabase-specific - both would affect local Docker Postgres
migrations too, and are now fixed with regression tests
(`backend/tests/test_db_preflight.py`):

1. **Percent-encoded passwords broke Alembic's `Config`.**
   `config.set_main_option("sqlalchemy.url", url)` stores the value through
   `configparser`, whose interpolation raises `ValueError` on a bare `%` -
   exactly what percent-encoding a password (per `docs/SUPABASE_SETUP.md`)
   produces. Fixed in `backend/database/migrations/env.py` and
   `backend/scripts/db_preflight.py` by escaping `%` as `%%` before handing
   the DSN to `Config`.
2. **Offline downgrade-render check always reported `False`.**
   `_check_downgrade_renders()` called `command.downgrade(cfg, "-1",
   sql=True)`; offline (`--sql`) mode never queries the target for
   "current", so a relative revision is ambiguous and Alembic raises
   `CommandError`. Fixed with an explicit `head:-1` range - re-verified
   against local Docker Postgres afterward (now also reports `True` there;
   this was silently wrong in every environment before today).

## TLS enforcement follow-up (Codex merge-block)

Codex reviewed this branch and blocked merge with a real finding:
`APP_ENV=staging|production` required `DATABASE_URL` to be *set*, but
never verified it actually used TLS - `sslmode=disable`, a missing
`sslmode`, or `DATABASE_SSL_MODE` left unset all passed silently, and
`db_preflight.py` only warned rather than failing.

Fixed with `backend/core/tls.py` as the single canonical TLS
implementation, used both by `Settings` (raises at construction time -
the backstop covering every entry point: uvicorn, Alembic, preflight) and
by `db_preflight.py`'s own explicit check. Staging/production now accepts
only `require`/`verify-ca`/`verify-full`, rejects everything else
(including a DSN that already declares a weak `sslmode` even when
`DATABASE_SSL_MODE=require` - that conflict must hard-fail, never resolve
silently in the safe direction), and a DSN missing `sslmode` gets
`DATABASE_SSL_MODE` injected rather than falling back to libpq's own
insecure default (`prefer`).

Re-verified live end to end:

| Check | Result |
|---|---|
| Local Docker Postgres, `APP_ENV=local` | PASS - unaffected, no TLS lines, connects as before |
| `APP_ENV=staging` + `DATABASE_SSL_MODE=require` pointed at that same non-TLS local Postgres | PASS (correctly fails to connect - proves TLS is actually requested, not just reported) |
| Supabase preflight, `--target runtime --expect-staging` | PASS - `Runtime TLS: PASS (sslmode=require)` and `Migration TLS: PASS (sslmode=require)` both printed, revision unchanged at `0003` |
| Chatbot smoke (`POST /api/chatbot/chat`) | PASS, over the enforced connection |
| Scan-history smoke (`POST /api/tools/url-scan`, list, delete) | PASS, over the enforced connection |

One gap found and closed during this session's own verification of the
fix: an earlier draft let `db_preflight.py` report `TLS: PASS` via the
`DATABASE_SSL_MODE` fallback while the literal `target_url` handed to
`create_engine()` a few lines later still carried no `sslmode` at all -
the check and the actual connection could diverge. Fixed by normalizing
`target_url` with the same `apply_ssl_mode()` Settings' own properties
use, before both the check and the connection.

35 new/updated tests across `backend/tests/test_tls.py`,
`test_supabase_settings.py`, and `test_db_preflight.py` - reading the
*effective* `settings.database_url`/`database_migration_url` (the exact
strings passed to SQLAlchemy/Alembic) via `dsn_sslmode()`, not a
superficial substring check. Full suite: 352 passed, 91.75% coverage,
ruff clean, bandit clean, pip-audit clean.

## What this run did not cover

Steps 16 and 17 were not independently re-exercised against Supabase in
this session (no code path touching them changed, and Phase 2's own test
suite plus the Docker Postgres run already covered them on the same
schema). Everything else above has direct command-level evidence from a
live Supabase project, not Docker Postgres.

`PHASE_2_5A_SUPABASE_REPORT.md` now records
`PHASE 2.5A SUPABASE CLOUD VALIDATION: PASS`.
