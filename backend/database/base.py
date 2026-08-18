"""Declarative base and shared column types for the ORM layer.

Phase 1.5 had no models at all; this module establishes the conventions that
every Phase 2+ table follows:

* **UUID primary keys** via :class:`sqlalchemy.Uuid`, which renders as a native
  ``UUID`` column on PostgreSQL and as ``CHAR(32)`` on SQLite, so the test
  suite can create the same schema without a Postgres server.
* **Timezone-aware timestamps** (``TIMESTAMPTZ``) with a Python-side default of
  :func:`backend.core.timeutils.utcnow` in addition to ``server_default``, so
  an ORM insert produces an aware UTC value on every backend.
* **JSON metadata columns** typed as ``JSONB`` on PostgreSQL and plain ``JSON``
  elsewhere.
"""
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.core.timeutils import utcnow

#: JSON column that uses PostgreSQL's binary JSONB where available.
JSONVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

#: UUID column type shared by every primary/foreign key.
UuidType = sa.Uuid(as_uuid=True)


class Base(DeclarativeBase):
    """Declarative base for all application models."""


class UuidPrimaryKeyMixin:
    """Adds a client-generated UUID primary key.

    The value is generated in Python rather than by a database default so the
    application knows the id before the flush completes and so the same code
    path works identically on PostgreSQL and SQLite.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UuidType,
        primary_key=True,
        default=uuid.uuid4,
    )


class CreatedAtMixin:
    """Adds an immutable ``created_at`` timestamp."""

    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.func.now(),
    )


class TimestampMixin(CreatedAtMixin):
    """Adds ``created_at`` plus an ``updated_at`` maintained on every update."""

    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=sa.func.now(),
    )
