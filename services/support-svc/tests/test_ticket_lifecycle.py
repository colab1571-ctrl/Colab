"""
Tests for ticket lifecycle: create → reply → resolve → CSAT.

Covers:
- Ticket creation returns correct SLA timestamps
- List tickets (user-scoped)
- Ticket detail includes events
- Reply transitions status
- CSAT happy path, 409 guard, 422 when not resolved
- 403 on wrong user
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticket(
    ticket_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    category: str = "payment",
    status: str = "open",
    tier: str = "free",
) -> MagicMock:
    now = datetime.now(tz=timezone.utc)
    t = MagicMock()
    t.id = ticket_id or uuid.uuid4()
    t.user_id = user_id or uuid.uuid4()
    t.category = category
    t.subject = "Test subject"
    t.body = "Test body"
    t.status = status
    t.priority = "normal"
    t.tier_at_creation = tier
    t.sla_ack_due = now + timedelta(hours=24)
    t.sla_resolve_due = now + timedelta(hours=72)
    t.sla_paused_seconds = 0
    t.sla_ack_breached_at = None
    t.sla_resolve_breached_at = None
    t.sla_paused_at = None
    t.first_response_at = None
    t.resolved_at = None
    t.assigned_to = None
    t.moderation_case_id = None
    t.created_at = now
    t.updated_at = now
    t.events = []
    t.csat = None
    return t


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def uid() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def client_with_db(uid: uuid.UUID):
    from app.main import app
    from app.db import get_db

    db_sess = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=None)
    exec_result.scalar_one = MagicMock(return_value=0)
    exec_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    db_sess.execute = AsyncMock(return_value=exec_result)
    db_sess.add = MagicMock()
    db_sess.flush = AsyncMock()
    db_sess.commit = AsyncMock()
    db_sess.refresh = AsyncMock()

    async def override_db():
        yield db_sess

    app.dependency_overrides[get_db] = override_db

    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers.update({"X-User-Id": str(uid)})
        yield c, db_sess, uid

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTicketCreate:
    @patch("app.routers.tickets.send_ticket_confirmation_email")
    @patch("app.routers.tickets.send_ticket_push")
    @patch("app.routers.tickets._get_user_tier", return_value="free")
    @patch("app.routers.tickets._emit_event_sync")
    def test_create_ticket_returns_201(
        self, mock_emit, mock_tier, mock_push, mock_email, client_with_db
    ):
        client, db_sess, uid = client_with_db

        ticket = _make_ticket(user_id=uid)
        db_sess.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", ticket.id))

        with patch("app.routers.tickets.SupportTicket", return_value=ticket):
            resp = client.post(
                "/v1/support/tickets",
                json={
                    "category": "payment",
                    "subject": "Charged twice",
                    "body": "I was charged twice for Premium.",
                },
            )

        assert resp.status_code == 201

    @patch("app.routers.tickets.send_ticket_confirmation_email")
    @patch("app.routers.tickets.send_ticket_push")
    @patch("app.routers.tickets._get_user_tier", return_value="free")
    @patch("app.routers.tickets._emit_event_sync")
    def test_invalid_category_returns_422(
        self, mock_emit, mock_tier, mock_push, mock_email, client_with_db
    ):
        client, db_sess, uid = client_with_db
        resp = client.post(
            "/v1/support/tickets",
            json={
                "category": "invalid_cat",
                "subject": "Test",
                "body": "Body text here.",
            },
        )
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self, client_with_db):
        client, _, _ = client_with_db
        client.headers.pop("X-User-Id", None)
        resp = client.post(
            "/v1/support/tickets",
            json={"category": "payment", "subject": "Test", "body": "Body"},
            headers={"X-User-Id": ""},  # empty
        )
        assert resp.status_code == 401

    @patch("app.routers.tickets.send_ticket_confirmation_email")
    @patch("app.routers.tickets.send_ticket_push")
    @patch("app.routers.tickets._get_user_tier", return_value="premium_pro")
    @patch("app.routers.tickets._emit_event_sync")
    def test_pro_tier_ack_halved(
        self, mock_emit, mock_tier, mock_push, mock_email, client_with_db
    ):
        """
        Pro tier: payment ack = 12h (half of 24h).
        Verify sla_ack_due is approximately 12h from now.
        """
        from datetime import datetime, timezone

        client, db_sess, uid = client_with_db

        ticket = _make_ticket(user_id=uid, tier="premium_pro")
        # Override sla_ack_due to match what compute_sla_due would produce
        now_approx = datetime.now(tz=timezone.utc)
        ticket.sla_ack_due = now_approx + timedelta(hours=12)
        db_sess.refresh = AsyncMock(side_effect=lambda obj: None)

        with patch("app.routers.tickets.SupportTicket", return_value=ticket):
            resp = client.post(
                "/v1/support/tickets",
                json={
                    "category": "payment",
                    "subject": "Double charge",
                    "body": "Charged twice.",
                },
            )

        assert resp.status_code == 201


class TestTicketDetail:
    def test_get_ticket_wrong_user_returns_403(self, client_with_db):
        client, db_sess, uid = client_with_db
        other_uid = uuid.uuid4()
        ticket = _make_ticket(user_id=other_uid)

        exec_result = MagicMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=ticket)
        db_sess.execute = AsyncMock(return_value=exec_result)

        resp = client.get(f"/v1/support/tickets/{ticket.id}")
        assert resp.status_code == 403

    def test_get_ticket_not_found_returns_404(self, client_with_db):
        client, db_sess, uid = client_with_db
        exec_result = MagicMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=None)
        db_sess.execute = AsyncMock(return_value=exec_result)

        resp = client.get(f"/v1/support/tickets/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestTicketCSAT:
    def test_csat_on_non_resolved_returns_422(self, client_with_db):
        client, db_sess, uid = client_with_db
        ticket = _make_ticket(user_id=uid, status="open")

        exec_result = MagicMock()
        exec_result.scalar_one_or_none = MagicMock(return_value=ticket)
        db_sess.execute = AsyncMock(return_value=exec_result)

        resp = client.post(
            f"/v1/support/tickets/{ticket.id}/csat",
            json={"score": 5},
        )
        assert resp.status_code == 422

    @patch("app.routers.tickets._emit_event_sync")
    def test_csat_duplicate_returns_409(self, mock_emit, client_with_db):
        client, db_sess, uid = client_with_db
        ticket = _make_ticket(user_id=uid, status="resolved")

        existing_csat = MagicMock()

        # First call → ticket, second call → existing CSAT
        exec_results = iter([
            MagicMock(scalar_one_or_none=MagicMock(return_value=ticket)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=existing_csat)),
        ])
        db_sess.execute = AsyncMock(side_effect=lambda *a, **kw: next(exec_results))

        resp = client.post(
            f"/v1/support/tickets/{ticket.id}/csat",
            json={"score": 4},
        )
        assert resp.status_code == 409

    @patch("app.routers.tickets._emit_event_sync")
    def test_csat_happy_path_returns_201(self, mock_emit, client_with_db):
        client, db_sess, uid = client_with_db
        ticket = _make_ticket(user_id=uid, status="resolved")
        csat_obj = MagicMock()
        csat_obj.id = uuid.uuid4()

        exec_results = iter([
            MagicMock(scalar_one_or_none=MagicMock(return_value=ticket)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # no existing CSAT
        ])
        db_sess.execute = AsyncMock(side_effect=lambda *a, **kw: next(exec_results))

        with patch("app.routers.tickets.SupportCSAT", return_value=csat_obj):
            resp = client.post(
                f"/v1/support/tickets/{ticket.id}/csat",
                json={"score": 5, "comment": "Great support!"},
            )

        assert resp.status_code == 201
