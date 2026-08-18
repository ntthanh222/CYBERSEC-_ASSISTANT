# Phase 2.5B RLS Policies

Migration `0004_auth_ownership_and_rls.py` is the canonical source for the
Phase 2.5B database authorization model.

## Tables

- `conversations`: `user_id uuid NOT NULL`, FK to `auth.users(id)`.
  Policy `conversations_owner_only` allows all actions only when
  `auth.uid() = user_id`.
- `security_scan_history`: `user_id uuid NOT NULL`, FK to
  `auth.users(id)`. Policy `security_scan_history_owner_only` allows all
  actions only when `auth.uid() = user_id`.
- `messages`: no separate `user_id`; ownership is derived through the
  parent `conversations` row. Policy
  `messages_via_owning_conversation` allows actions only when the parent
  conversation belongs to `auth.uid()`.

All three tables have row level security enabled and forced. The backend
request-scoped DB dependency runs `SET LOCAL ROLE authenticated` and sets
`request.jwt.claims` for the verified Supabase user before querying.

## Migration Safety

Codex blocked commit `02d7042` because the first `0004` implementation
deleted legacy application rows. Commit `2621150` makes the migration
non-destructive: before any DDL or policy work, it counts rows in
`conversations`, `messages`, and `security_scan_history`. Any non-zero
count blocks the migration with a count-only error:

`Migration 0004 blocked: legacy rows without an authenticated owner exist. conversations=<count>, messages=<count>, security_scan_history=<count>. No data was modified. Resolve ownership manually before retrying.`

No row contents, credentials, or DSNs are included in that error. The
fixed migration contains no `DELETE FROM`, no `TRUNCATE`, and no default
owner assignment.
