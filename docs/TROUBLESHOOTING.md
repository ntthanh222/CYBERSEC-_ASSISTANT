# Troubleshooting

## Frontend shows a blank page in a Docker deployment

Fixed in Phase 2.7A (`frontend/Dockerfile`) — if this recurs, check that
the Dockerfile's builder stage (`npm ci && npm run build`) still exists and
that the nginx stage copies from `--from=builder /app/dist/...`, not from
the repo root. Confirm with:

```bash
curl -s http://<frontend-origin>/ | grep -o 'src="[^"]*"'
```

Expect `src="/assets/index-<hash>.js"`. If it instead shows
`src="/src/main.tsx"`, the image is serving the unbuilt dev-mode template —
see `PHASE_2_7A_RELEASE_HARDENING_REPORT.md` for the full root cause.

## Frontend loads but every API call fails silently

Check the browser console for a Content-Security-Policy violation on
`connect-src 'self'`. This means `VITE_API_BASE_URL` was baked in as an
absolute cross-origin URL (e.g. `http://localhost:8000`) at build time
instead of the same-origin default. `frontend/src/lib/api/client.ts`
defaults to `''` (relative, proxied by `nginx.conf`'s `/api/` block) as of
Phase 2.7A; only set `VITE_API_BASE_URL` explicitly for local
`npm run dev` against a bare backend on a different port.

## `pip-audit` / `pip install` fails with a TLS certificate error on Windows

Symptom: `OSError: Could not find a suitable TLS CA certificate bundle,
invalid path: C:\...`. Caused by a stray `CURL_CA_BUNDLE` (or similar)
environment variable pointing at a nonexistent path. Point it at the
venv's own certifi bundle instead:

```bash
CURL_CA_BUNDLE="<path-to-venv>/Lib/site-packages/certifi/cacert.pem" python -m pip_audit
```

## `docker exec`/`docker cp`/`pg_restore` "file not found" on Windows Git Bash

Git Bash's MSYS layer rewrites leading-`/` arguments (e.g. `/tmp/foo`) into
Windows host paths before they ever reach `docker`, breaking any command
whose argument is meant to be a path *inside* the container. Set
`MSYS_NO_PATHCONV=1` for that single command:

```bash
MSYS_NO_PATHCONV=1 docker exec my-container pg_restore -U user -d db /tmp/backup.dump
```

## A local Supabase CLI stack (`supabase start`) crashes unprompted

Observed twice in Phase 2.7A on this host — containers reported
`unhealthy`/`marked for removal` shortly after a clean start, even with
non-essential services (`studio`, `storage`, `realtime`, `edge_runtime`,
`analytics`) disabled in `supabase/config.toml`. Treated as a genuine
environment-stability issue rather than chased further; UAT fell back to
minting a test-safe session directly (see `docs/UAT.md`). If this is
needed again, try `supabase stop` then `supabase start` once more before
concluding it's unusable — the first retry succeeded briefly in this
session before crashing again on the next container recreate.
