"""
Regression test for RESUME gap #2.

`least_participant` and `greatest_participant` are GENERATED ALWAYS STORED
columns in collab.collaboration (see alembic 20260511_0001). Postgres rejects
any INSERT that supplies a value for those columns, so the create-collab
service must NOT include them in `.values(...)`.

We verify this at the SQL compilation level (no live DB needed):
  1. The compiled INSERT must not reference `least_participant` or
     `greatest_participant`.
  2. The function still computes `least`/`greatest` locally for the
     on-conflict lookup, so we exercise create_collaboration via a stubbed
     AsyncSession and check the statement it actually executed.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.models import Collaboration
from app.services.collab_service import create_collaboration


def _compile(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )


@pytest.mark.asyncio
async def test_create_collaboration_insert_omits_generated_columns():
    """The INSERT statement must not list least_participant/greatest_participant."""
    profile_a = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
    profile_b = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

    # Mock AsyncSession that captures the executed statement.
    executed_stmts: list = []

    async def _execute(stmt, *args, **kwargs):
        executed_stmts.append(stmt)
        result = MagicMock()
        # First call (the INSERT) should return a row so the lookup branch
        # is skipped — keeps the test focused on the INSERT SQL.
        row = MagicMock(spec=Collaboration)
        row.id = uuid.uuid4()
        row.profile_id_a = profile_a
        row.profile_id_b = profile_b
        scalars = MagicMock()
        scalars.first.return_value = row
        scalars.one.return_value = row
        result.scalars.return_value = scalars
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    db.commit = AsyncMock()

    await create_collaboration(db, profile_a, profile_b)

    assert executed_stmts, "create_collaboration did not execute any SQL"
    insert_stmt = executed_stmts[0]
    compiled = _compile(insert_stmt).lower()

    # The compiled INSERT must not mention the GENERATED columns at all
    # (Postgres would reject the row otherwise).
    assert "least_participant" not in compiled, (
        f"INSERT still references generated column least_participant: {compiled}"
    )
    assert "greatest_participant" not in compiled, (
        f"INSERT still references generated column greatest_participant: {compiled}"
    )

    # Sanity: it IS still an INSERT into collaboration with the raw profile ids.
    assert "insert into" in compiled
    assert "collaboration" in compiled
    assert "profile_id_a" in compiled
    assert "profile_id_b" in compiled


def test_collaboration_model_still_exposes_generated_columns():
    """
    The ORM must still know about the columns so SELECT/WHERE queries
    (e.g. the on-conflict fallback) keep working.
    """
    cols = {c.name for c in Collaboration.__table__.columns}
    assert "least_participant" in cols
    assert "greatest_participant" in cols
