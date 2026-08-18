# Backup / Restore

## Backup

```powershell
scripts\Backup-Database.ps1
scripts\Backup-Database.ps1 -OutputDir backups
```

- Checks `postgres` is `healthy` before running; fails clearly otherwise.
- Runs `pg_dump -Fc` (custom format, compressed, restorable with
  `pg_restore`) inside the `postgres` container via `docker compose exec`.
- Output filename: `<db_name>_<yyyyMMdd_HHmmss>.dump`, written to
  `backups/` (gitignored — dumps are never committed).
- Never prints the database password; credentials come from the
  container's own environment.
- Exits non-zero and deletes a zero-byte output file if `pg_dump` fails.

## Restore

```powershell
scripts\Restore-Database.ps1 -BackupFile backups\cybersec_assistant_20260729_031500.dump
scripts\Restore-Database.ps1 -BackupFile <path> -Force   # non-interactive, for CI/scripts
```

- Requires an existing backup file path; fails if it doesn't exist.
- Prints a warning that the target database will be dropped and
  recreated, and requires typing `yes` to continue unless `-Force` is
  passed.
- Copies the dump into the `postgres` container, then runs
  `pg_restore --clean --if-exists --no-owner`.
- Verifies the restore by confirming `schema_bootstrap` exists and the
  database is queryable afterward — a restore that "succeeds" but leaves
  an empty/broken database is treated as a failure.
- Never touches the `postgres_data` Docker volume directly.

## Real test performed (2026-07-29)

A live backup/restore cycle was run against the running `postgres`
container (docker commands identical to what the scripts above wrap):

1. Inserted a canary row (`demo_seed_marker.seed_key = 'backup-restore-canary'`).
2. `pg_dump -Fc` → `backups/cybersec_assistant_test.dump` (6370 bytes).
3. **Destroyed** the data: deleted the canary row and `DROP TABLE schema_bootstrap`.
4. Confirmed destruction: `SELECT COUNT(*) FROM demo_seed_marker` → `0`;
   `to_regclass('public.schema_bootstrap')` → `NULL`.
5. Copied the dump into the container and ran
   `pg_restore -U cybersec -d cybersec_assistant --clean --if-exists --no-owner` → exit code `0`.
6. Verified: `demo_seed_marker.seed_key` → `backup-restore-canary` (back),
   `to_regclass('public.schema_bootstrap')` → `schema_bootstrap` (back),
   and `GET /api/system/health` on the live backend returned
   `"database":{"status":"healthy"}` immediately after — proving the
   restored database is actually usable, not just present.

Full evidence and command output: `.ai/BACKUP_RESTORE_REPORT.md`.

## Notes

- The Windows dev host's Git Bash/MSYS shell rewrites leading-`/` container
  paths (e.g. `/tmp/...`) into host paths unless `MSYS_NO_PATHCONV=1` is set
  — this only affects manual shell testing, not the PowerShell scripts
  (PowerShell has no such path-mangling behavior).
- Dump files are never committed to Git (`backups/` is gitignored).

## Phase 2.7A: cross-container restore drill (pgvector-aware)

Re-verified the same drill against a database that also has migration
0005's pgvector schema (`knowledge_documents`/`knowledge_chunks`) applied,
restoring into a **brand-new** disposable container rather than back into
the same one:

1. Created a marker-tagged test document via the real ingest API.
2. `pg_dump -F c` from the source container.
3. Restored into a fresh `pgvector/pgvector:pg16` container with
   `pg_restore --no-owner --no-privileges`.
4. Verified in the restored database: `pgvector` extension `0.8.5` present,
   `alembic_version` = `0005` (head), the document row and its chunk/
   embedding both present with 0 NULL embeddings.
5. Ran a real `PgVectorRagRetriever.retrieve()` call against the *restored*
   database — returned the correct document.
6. Tore down the restore-target container and the temporary dump file.

Confirms restore works even when the target has never run migrations
before (a fresh `pgvector/pgvector:pg16` image, not a copy of the source)
and that vector data survives dump/restore intact. Full narrative:
`PHASE_2_7A_RELEASE_HARDENING_REPORT.md`.
