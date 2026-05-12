"""
support-svc — Ticket CRUD endpoints.

POST   /v1/support/tickets           create ticket
GET    /v1/support/tickets           list user's tickets
GET    /v1/support/tickets/{id}      ticket detail + events
POST   /v1/support/tickets/{id}/reply     add reply
POST   /v1/support/tickets/{id}/csat      submit CSAT
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_support_settings
from app.db import get_db
from app.models import SupportCSAT, SupportTicket, SupportTicketEvent
from app.schemas import (
    CSATCreate,
    CSATOut,
    ReplyCreate,
    ReplyOut,
    TicketCreate,
    TicketDetailOut,
    TicketEventOut,
    TicketListOut,
    TicketOut,
)
from app.sla import compute_sla_due
from app.workers.tasks import (
    embed_kb_article,
    send_ticket_confirmation_email,
    send_ticket_push,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/support/tickets", tags=["tickets"])

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _require_user(request: Request) -> uuid.UUID:
    user_id_str = request.headers.get("X-User-Id")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")


# ---------------------------------------------------------------------------
# Tier lookup
# ---------------------------------------------------------------------------

_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        cfg = get_support_settings()
        _redis_client = aioredis.from_url(cfg.redis_url, decode_responses=True)
    return _redis_client


async def _get_user_tier(user_id: uuid.UUID) -> str:
    """
    Query billing-svc for user subscription tier.
    Result cached in Redis for 5 min TTL.
    Defaults to 'free' on timeout/error (spec R-005).
    """
    cfg = get_support_settings()
    r = _get_redis()
    cache_key = f"user:{user_id}:tier"

    cached = await r.get(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{cfg.billing_svc_url}/internal/users/{user_id}/tier",
                headers={"X-Service": "support-svc"},
            )
            if resp.status_code == 200:
                tier = resp.json().get("tier", "free")
            else:
                tier = "free"
    except Exception as exc:
        logger.warning("Billing-svc tier lookup failed for %s: %s", user_id, exc)
        tier = "free"

    await r.set(cache_key, tier, ex=cfg.billing_tier_cache_ttl)
    return tier


# ---------------------------------------------------------------------------
# RabbitMQ event emit (best-effort)
# ---------------------------------------------------------------------------


def _emit_event_sync(event_name: str, payload: dict) -> None:
    """Best-effort synchronous RabbitMQ publish for ticket creation side-effects."""
    try:
        import pika

        cfg = get_support_settings()
        params = pika.URLParameters(cfg.rabbitmq_url)
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        domain = event_name.split(".")[0]
        channel.exchange_declare(exchange=domain, exchange_type="topic", durable=True)
        channel.basic_publish(
            exchange=domain,
            routing_key=event_name,
            body=json.dumps({"event": event_name, "data": payload}).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
            ),
        )
        connection.close()
    except Exception as exc:
        logger.warning("Event emit failed [%s]: %s", event_name, exc)


# ---------------------------------------------------------------------------
# POST /v1/support/tickets
# ---------------------------------------------------------------------------


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    user_id = _require_user(request)
    tier = await _get_user_tier(user_id)
    now = datetime.now(tz=timezone.utc)
    sla_ack_due, sla_resolve_due = compute_sla_due(body.category, tier, now)

    ticket = SupportTicket(
        user_id=user_id,
        category=body.category,
        subject=body.subject,
        body=body.body,
        status="open",
        priority="normal",
        tier_at_creation=tier,
        sla_ack_due=sla_ack_due,
        sla_resolve_due=sla_resolve_due,
    )
    db.add(ticket)
    await db.flush()

    # Creation event
    event = SupportTicketEvent(
        ticket_id=ticket.id,
        kind="created",
        actor="user",
        actor_id=user_id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(ticket)

    ticket_id_str = str(ticket.id)

    # Side-effects: email + push (enqueue via Celery)
    try:
        send_ticket_confirmation_email.delay(ticket_id_str)
        send_ticket_push.delay(ticket_id_str)
    except Exception as exc:
        logger.warning("Could not enqueue notification tasks for %s: %s", ticket_id_str, exc)

    # Cross-link harassment/IP tickets to moderation-svc
    if body.category in ("harassment_threats", "ip_dmca"):
        _emit_event_sync(
            "support.ticket.created",
            {
                "ticket_id": ticket_id_str,
                "user_id": str(user_id),
                "category": body.category,
            },
        )

    return TicketOut.model_validate(ticket)


# ---------------------------------------------------------------------------
# GET /v1/support/tickets
# ---------------------------------------------------------------------------


@router.get("", response_model=TicketListOut)
async def list_tickets(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> TicketListOut:
    user_id = _require_user(request)

    stmt = select(SupportTicket).where(SupportTicket.user_id == user_id)
    if status_filter:
        stmt = stmt.where(SupportTicket.status == status_filter)

    total_result = await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )
    total = total_result.scalar_one()

    stmt = stmt.order_by(SupportTicket.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    tickets = result.scalars().all()

    return TicketListOut(
        tickets=[TicketOut.model_validate(t) for t in tickets],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# GET /v1/support/tickets/{id}
# ---------------------------------------------------------------------------


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TicketDetailOut:
    user_id = _require_user(request)
    is_agent = request.headers.get("X-User-Role") in ("support_agent", "admin")

    result = await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if ticket.user_id != user_id and not is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return TicketDetailOut(
        ticket=TicketOut.model_validate(ticket),
        events=[TicketEventOut.model_validate(e) for e in ticket.events],
    )


# ---------------------------------------------------------------------------
# POST /v1/support/tickets/{id}/reply
# ---------------------------------------------------------------------------


@router.post("/{ticket_id}/reply", response_model=ReplyOut, status_code=status.HTTP_201_CREATED)
async def reply_ticket(
    ticket_id: uuid.UUID,
    body: ReplyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReplyOut:
    user_id = _require_user(request)
    is_agent = request.headers.get("X-User-Role") in ("support_agent", "admin")
    actor = "agent" if is_agent else "user"

    result = await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if ticket.user_id != user_id and not is_agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    now = datetime.now(tz=timezone.utc)

    # Set first_response_at if agent replies and not yet set
    if actor == "agent" and ticket.first_response_at is None:
        ticket.first_response_at = now
        ticket.status = "in_progress"

    # Resume SLA clock if user replies on pending_user ticket
    if actor == "user" and ticket.status == "pending_user":
        if ticket.sla_paused_at:
            paused_delta = int((now - ticket.sla_paused_at).total_seconds())
            ticket.sla_paused_seconds = (ticket.sla_paused_seconds or 0) + paused_delta
            ticket.sla_paused_at = None
        ticket.status = "in_progress"

    event = SupportTicketEvent(
        ticket_id=ticket.id,
        kind="reply",
        actor=actor,
        actor_id=user_id,
        body=body.body,
    )
    db.add(event)
    ticket.updated_at = now
    await db.commit()
    await db.refresh(event)

    return ReplyOut(event_id=event.id, created_at=event.created_at)


# ---------------------------------------------------------------------------
# POST /v1/support/tickets/{id}/csat
# ---------------------------------------------------------------------------


@router.post("/{ticket_id}/csat", response_model=CSATOut, status_code=status.HTTP_201_CREATED)
async def submit_csat(
    ticket_id: uuid.UUID,
    body: CSATCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CSATOut:
    user_id = _require_user(request)

    result = await db.execute(
        select(SupportTicket).where(SupportTicket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if ticket.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if ticket.status != "resolved":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSAT can only be submitted for resolved tickets",
        )

    # 409 guard: check unique constraint
    existing = await db.execute(
        select(SupportCSAT).where(SupportCSAT.ticket_id == ticket_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CSAT already submitted")

    csat = SupportCSAT(
        ticket_id=ticket_id,
        score=body.score,
        comment=body.comment,
    )
    db.add(csat)

    # Log CSAT event
    db.add(SupportTicketEvent(
        ticket_id=ticket_id,
        kind="csat",
        actor="user",
        actor_id=user_id,
        body=str(body.score),
        metadata={"score": body.score},
    ))

    await db.commit()
    await db.refresh(csat)

    # Emit analytics event (best-effort)
    _emit_event_sync(
        "support.csat.submitted",
        {
            "ticket_id": str(ticket_id),
            "user_id": str(user_id),
            "score": body.score,
        },
    )

    return CSATOut(csat_id=csat.id)
