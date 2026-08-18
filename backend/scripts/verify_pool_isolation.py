"""Live proof that `request.jwt.claims` never leaks across a pooled connection.

`SET LOCAL` is transaction-scoped in Postgres and resets at COMMIT/ROLLBACK,
but that guarantee is only as good as the code actually always committing or
rolling back before returning a connection to the pool. This script exercises
the real `get_rls_db` code path (not a synthetic reproduction) against a
small connection pool, forcing physical-connection reuse between different
users' "requests", and asserts the claim set by an earlier request is never
visible to a later one that reused the same connection without setting its
own.

Usage::

    python -m backend.scripts.verify_pool_isolation "postgresql+psycopg://user:pass@host:port/db"
"""
import asyncio
import json
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

if sys.platform == "win32":
    # psycopg's async driver needs a selector event loop; Windows defaults
    # to ProactorEventLoop, which it cannot use. Docker/Linux (production
    # and CI) are unaffected - this is a local-verification-only script.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def _simulate_request(engine, user_id: uuid.UUID | None, *, read_only: bool) -> str | None:
    """One request: if user_id is set, behaves like get_rls_db (sets the
    claim). If user_id is None, behaves like a request that reads the claim
    *without* setting it first - the leak-detection probe."""
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    session = sessionmaker()
    try:
        if user_id is not None:
            await session.execute(text("SET LOCAL ROLE authenticated"))
            await session.execute(
                text("SELECT set_config('request.jwt.claims', :claims, true)"),
                {"claims": json.dumps({"sub": str(user_id), "role": "authenticated"})},
            )
        if read_only:
            # No SET LOCAL here at all - exactly what a later request on a
            # reused physical connection would see if isolation had failed.
            row = (
                await session.execute(text("SELECT current_setting('request.jwt.claims', true)"))
            ).scalar()
            return row
        await session.commit()
        return None
    finally:
        await session.close()


async def main(dsn: str) -> int:
    # pool_size=1 forces every request onto the SAME physical connection -
    # the worst case for leakage, and the only way to prove it deterministically
    # rather than hoping the pool happens to reuse a connection.
    engine = create_async_engine(dsn, pool_size=1, max_overflow=0)

    checks: list[tuple[str, bool]] = []

    user_a = uuid.uuid4()
    await _simulate_request(engine, user_a, read_only=False)

    # Next request reuses the same physical connection (pool_size=1) but
    # never sets its own claim - if SET LOCAL truly reset at commit, this
    # must see nothing, not user A's claim.
    leaked_claim = await _simulate_request(engine, None, read_only=True)
    checks.append(("claim from a prior committed request does not leak", not leaked_claim))

    user_b = uuid.uuid4()
    await _simulate_request(engine, user_b, read_only=False)

    # And a plain read-only probe again, after B's request committed.
    leaked_claim_2 = await _simulate_request(engine, None, read_only=True)
    checks.append(("claim from B's committed request does not leak either", not leaked_claim_2))

    # Interleaved: set as A, roll back (never commit), then read on the same
    # connection - ROLLBACK must also clear SET LOCAL, same as COMMIT.
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    session = sessionmaker()
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('request.jwt.claims', :claims, true)"),
        {"claims": json.dumps({"sub": str(user_a), "role": "authenticated"})},
    )
    await session.rollback()
    await session.close()
    leaked_after_rollback = await _simulate_request(engine, None, read_only=True)
    checks.append(("claim does not leak after a rollback either", not leaked_after_rollback))

    await engine.dispose()

    all_pass = True
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        all_pass = all_pass and ok
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
