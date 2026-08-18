# Local backup and restore

Two PowerShell utilities under `scripts/`. Neither is required to run the
app - `docker compose up -d --build` never depends on them - they exist
purely as an operational safety net for anyone running this stack for real
local use.

## `Backup-Database.ps1`

```powershell
cd "D:\đồ án1"
powershell -File scripts\Backup-Database.ps1
```

- Dumps Postgres with `pg_dump -Fc` (compressed, `pg_restore`-compatible)
  from inside the `postgres` container, then copies the dump out with
  `docker compose cp` - never through PowerShell's own stdout redirection,
  which would silently corrupt the binary dump format by re-encoding it as
  text.
- Refuses to run if `postgres` isn't reporting healthy.
- Verifies the resulting file is non-empty before declaring success;
  deletes it and fails loudly if it's empty.
- Writes a `<dump>.meta.json` sidecar alongside every dump: timestamp,
  database name, the Alembic migration revision, the installed `pgvector`
  extension version, the app's own git commit, and the dump's size. Never
  a password, DSN, or secret - metadata only.
- Default output: `backups/local/` under the project root (override with
  `-OutputDir`).

## `Restore-Database.ps1`

```powershell
cd "D:\đồ án1"
powershell -File scripts\Restore-Database.ps1 -BackupFile "backups\local\cybersec_assistant_....dump"
```

Never blindly overwrites the live database. Three steps, in order, each
gated on the previous one succeeding:

1. **Safety-backs up the current state first**, via `Backup-Database.ps1`
   itself, into `backups/pre-restore-safety/` - so a bad restore is always
   recoverable, before anything else happens.
2. **Restores into a disposable database** (`<dbname>_restore_verify`,
   created and dropped inside the same Postgres instance) and verifies it
   actually contains the expected schema and migration revision. If the
   dump is truncated, wrong-schema, or otherwise suspect, this step fails
   and **the real database is never touched**.
3. **Only then** restores into the real database (`pg_restore --clean
   --if-exists`) and re-verifies it afterward.

Requires an explicit `yes` confirmation (or `-Force` for scripted use).
Never uses `docker compose down -v`.

## Verified end-to-end (local-final-hardening)

Run for real against the disposable `cybersec-final-fresh` test project,
not simulated:

1. Created a real document (via `POST /api/knowledge/documents`, uploaded
   through the actual ingestion pipeline - chunked and embedded) and a
   real conversation with a chat turn, both with a unique marker.
2. `Backup-Database.ps1` - produced a non-empty `.dump` plus a metadata
   sidecar reporting `migration=0005 pgvector=0.8.5`.
3. `Restore-Database.ps1 -Force` - safety-backed up current state,
   restored into the disposable `cybersec_assistant_restore_verify`
   database and verified it, dropped it, then restored into the real
   database.
4. Verified afterward, via a direct query: migration `0005`, pgvector
   `0.8.5`, the marker document (1 row), its chunk (1 row, embedding
   `vector_dims = 384` - the expected embedding dimension), the marker
   conversation (2 rows including a second pre-existing one), and its
   message (2 rows) - all present and correct.
5. Confirmed the disposable verification database no longer exists after
   the run (`SELECT datname FROM pg_database WHERE datname LIKE
   '%restore_verify%'` returned no rows).

No data lost, no orphaned disposable database left behind, root's own data
never touched (this drill ran entirely against the disposable test
project).
