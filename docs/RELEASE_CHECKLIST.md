# Release Checklist — v0.2.7-rc1

Use this before promoting `feature/phase-2` toward `main` or a real
deployment. Each item links to where it was last verified.

## Build

- [ ] `frontend/Dockerfile` builder stage runs `npm run build` and the
      nginx stage copies from `dist/` — see `docs/TROUBLESHOOTING.md`
      "blank page" entry if unsure.
- [ ] `frontend/src/lib/api/client.ts`'s `API_BASE_URL` default is `''`
      (same-origin), not an absolute cross-origin URL.
- [ ] `nginx.conf`'s CSP `connect-src` covers wherever the deployment's
      real Supabase Auth project actually lives, if using hosted Supabase
      Auth from the browser directly (known gap — not fixed in 2.7A, see
      `PHASE_2_7A_RELEASE_HARDENING_REPORT.md`).

## Tests

- [ ] Backend: `pytest backend/tests` (≥90% coverage), Ruff, Bandit,
      pip-audit all clean.
- [ ] Frontend: lint, type-check, `vitest run`, `npm run build` all clean.
- [ ] `frontend/e2e/` Playwright suite green on all 3 device projects.
- [ ] Container RAG smoke (`backend/scripts/verify_rag_container_smoke.py`)
      PASS inside a freshly-built backend image.

## Security

- [ ] Gitleaks full history and current tree both clean (or narrowly
      allowlisted with a documented audit — see `.gitleaksignore`).
- [ ] `git diff --check` clean.
- [ ] Frontend bundle scanned for server-side secret leakage.
- [ ] Trivy image scan reviewed at the package level, not just a raw
      finding count (see Phase 2.6's `.ai/SECURITY_REPORT.md` for the
      established methodology).

## Data

- [ ] Migrations apply cleanly to a fresh database (`alembic upgrade
      head` from empty).
- [ ] Backup/restore drill passes on a disposable database (see
      `docs/BACKUP_RESTORE.md`).
- [ ] RLS/two-user isolation re-verified after any auth or repository-layer
      change.

## Process

- [ ] Independent Codex (or equivalent) review PASS on the diff.
- [ ] Working tree clean before merge.
- [ ] Merge is `--no-ff` into the integration branch; no manual file copy.
- [ ] Full validation re-run **from the merge target**, not just the
      source worktree/branch.
- [ ] Generated caches/artifacts cleaned; no source, migration, or
      production data deleted in the process.
