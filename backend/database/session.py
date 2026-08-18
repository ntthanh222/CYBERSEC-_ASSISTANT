"""Async SQLAlchemy engine and session factory.

Engine construction is lazy: creating it never touches the network, so a
Postgres outage at import time cannot crash the process. Only an actual
probe/query attempt can fail, and callers are responsible for catching that.
"""
import json
from functools import lru_cache
from typing import AsyncIterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config.settings import get_settings
from backend.core.auth import AuthenticatedUser, get_current_user
from backend.core.db_retry import pg_connect_args


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        # Conservative on purpose: Supabase's Session Pooler is itself a
        # shared, connection-limited resource, so the app should not hold
        # more connections open than a small API service actually needs.
        pool_size=5,
        max_overflow=5,
        # Recycle before a mid-tier idle-connection timeout (e.g. a pooler
        # or firewall silently dropping a connection after ~10 minutes)
        # would otherwise surface as a confusing query-time error.
        pool_recycle=300,
        connect_args=pg_connect_args(settings.database_url),
        future=True,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session.

    The session is rolled back and closed on any exception so a failed request
    can never leave a half-applied transaction on the pooled connection. Commit
    is the caller's decision: read-only routes never commit.
    """
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_rls_db(
    user: AuthenticatedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AsyncIterator[AsyncSession]:
    """Request-scoped session that runs *as the authenticated caller*.

    Row Level Security policies key on ``auth.uid()``, which Postgres/Supabase
    resolve from the ``request.jwt.claims`` GUC under the ``authenticated``
    role - the same mechanism PostgREST uses for a direct-Postgres client.
    ``SET LOCAL`` scopes both statements to this request's transaction only;
    they never leak onto a pooled connection reused by a later request.

    This is defense in depth alongside the explicit ``user_id`` ownership
    checks each service performs - RLS is not a substitute for those checks,
    it is what still protects the data if a service-layer check is ever
    missing or wrong.
    """
    claims_json = json.dumps({"sub": str(user.id), "role": user.role})
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('request.jwt.claims', :claims, true)"),
        {"claims": claims_json},
    )
    yield session
