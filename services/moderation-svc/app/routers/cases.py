"""
moderation-svc — Moderator case management router.

M-011: claim/release/action endpoints
M-012: queue list + filters + detail + user-360 history
M-014: reopen + escalate
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import ModerationAction, ModerationCase
from app.schemas import (
    ActionResponse,
    CaseActionRequest,
    CaseDetail,
    CaseSummary,
)

router = APIRouter(prefix="/moderation", tags=["moderation"])


def _require_mod_role(request: Request) -> uuid.UUID:
    """Require mod or super-admin role claim from JWT (set by gateway)."""
    role = request.headers.get("X-User-Role", "")
    user_id = request.headers.get("X-User-Id", "")
    if role not in ("mod", "super_admin", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Moderator role required")
    try:
        return uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid moderator identity")


def _require_super_admin(request: Request) -> uuid.UUID:
    role = request.headers.get("X-User-Role", "")
    user_id = request.headers.get("X-User-Id", "")
    if role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super-admin role required")
    try:
        return uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid identity")


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


@router.get("/queue", response_model=list[CaseSummary])
async def get_queue(
    request: Request,
    tier: str | None = Query(None),
    sla: str | None = Query(None, description="'overdue' to filter SLA-breached cases"),
    subject_type: str | None = Query(None),
    forced_human: bool | None = Query(None),
    assigned_to: uuid.UUID | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    sess: AsyncSession = Depends(get_db),
) -> list[CaseSummary]:
    """Paginated mod queue, sorted by priority_tier desc + sla_due_at asc."""
    _require_mod_role(request)
    from sqlalchemy import asc, desc

    q = select(ModerationCase).where(ModerationCase.status.in_(["open", "in_review", "escalated"]))

    if tier:
        q = q.where(ModerationCase.priority_tier == tier)
    if sla == "overdue":
        now = datetime.now(tz=timezone.utc)
        q = q.where(ModerationCase.sla_due_at <= now)
    if subject_type:
        q = q.where(ModerationCase.subject_type == subject_type)
    if forced_human is not None:
        q = q.where(ModerationCase.forced_human == forced_human)
    if assigned_to:
        q = q.where(ModerationCase.claimed_by == assigned_to)

    q = q.order_by(desc(ModerationCase.priority_tier), asc(ModerationCase.sla_due_at))
    q = q.limit(limit).offset(offset)

    result = await sess.execute(q)
    cases = result.scalars().all()
    return [_case_to_summary(c) for c in cases]


@router.get("/cases/{case_id}", response_model=CaseDetail)
async def get_case(
    case_id: uuid.UUID,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> CaseDetail:
    _require_mod_role(request)
    case = await _get_case_or_404(sess, case_id)
    return _case_to_detail(case)


# ---------------------------------------------------------------------------
# Claim / Release
# ---------------------------------------------------------------------------


@router.post("/cases/{case_id}/claim")
async def claim_case(
    case_id: uuid.UUID,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> dict:
    """Set case status=in_review + claimed_by=me."""
    moderator_id = _require_mod_role(request)
    case = await _get_case_or_404(sess, case_id)
    if case.status not in ("open",):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Case status is '{case.status}', cannot claim")
    case.status = "in_review"
    case.claimed_by = moderator_id
    case.claimed_at = datetime.now(tz=timezone.utc)
    await sess.commit()
    return {"case_id": str(case_id), "status": "in_review", "claimed_by": str(moderator_id)}


@router.post("/cases/{case_id}/release")
async def release_case(
    case_id: uuid.UUID,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> dict:
    """Un-claim case back to open."""
    moderator_id = _require_mod_role(request)
    case = await _get_case_or_404(sess, case_id)
    if case.claimed_by != moderator_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You did not claim this case")
    case.status = "open"
    case.claimed_by = None
    case.claimed_at = None
    await sess.commit()
    return {"case_id": str(case_id), "status": "open"}


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

_DUAL_REVIEW_ACTIONS = {"permanent_ban", "delete_account"}


@router.post("/cases/{case_id}/action", response_model=ActionResponse)
async def take_action(
    case_id: uuid.UUID,
    body: CaseActionRequest,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> ActionResponse:
    """
    Apply a moderation action to a case.
    permanent_ban / delete_account require second_reviewer_id != reviewer_id.
    ModerationAction is append-only (DB trigger).
    """
    moderator_id = _require_mod_role(request)
    case = await _get_case_or_404(sess, case_id)

    if case.status not in ("in_review", "escalated"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Case must be in_review or escalated to take action",
        )

    if body.action_type in _DUAL_REVIEW_ACTIONS:
        if not body.second_reviewer_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{body.action_type}' requires second_reviewer_id",
            )
        if body.second_reviewer_id == moderator_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="second_reviewer_id must differ from the primary reviewer",
            )

    # forced_human cases cannot be auto-dismissed (plan §5.1)
    if body.action_type == "dismiss" and case.forced_human:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Forced-human cases cannot be auto-dismissed",
        )

    now = datetime.now(tz=timezone.utc)

    action = ModerationAction(
        case_id=case_id,
        action_type=body.action_type,
        reviewer_id=moderator_id,
        reason=body.reason,
        evidence_refs=body.evidence_refs or [],
        target_user_id=case.subject_owner_user_id,
        propagation_status="pending",
    )
    sess.add(action)

    # Update case
    case.actioned_at = now
    case.actioned_by = moderator_id
    case.action_type = body.action_type
    case.second_reviewer_id = body.second_reviewer_id
    case.status = "dismissed" if body.action_type == "dismiss" else "actioned"

    await sess.flush()
    await sess.commit()
    await sess.refresh(action)

    # Dispatch propagation async
    import uuid as _uuid
    from app.workers.propagation_tasks import dispatch_action

    propagation_id = str(_uuid.uuid4())
    dispatch_action.apply_async(
        kwargs={
            "action_id": str(action.id),
            "action_type": body.action_type,
            "target_user_id": str(case.subject_owner_user_id),
            "case_id": str(case_id),
            "reason": body.reason,
            "reviewer_id": str(moderator_id),
            "second_reviewer_id": str(body.second_reviewer_id) if body.second_reviewer_id else None,
        },
        countdown=0,
    )

    return ActionResponse(action_id=action.id, propagation_id=propagation_id)


# ---------------------------------------------------------------------------
# Escalate / Reopen
# ---------------------------------------------------------------------------


@router.post("/cases/{case_id}/escalate")
async def escalate_case(
    case_id: uuid.UUID,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> dict:
    moderator_id = _require_mod_role(request)
    case = await _get_case_or_404(sess, case_id)
    case.status = "escalated"
    await sess.commit()
    return {"case_id": str(case_id), "status": "escalated"}


@router.post("/cases/{case_id}/reopen")
async def reopen_case(
    case_id: uuid.UUID,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> dict:
    """Super-admin only. Creates a linked new case (append-only; does not mutate original)."""
    super_admin_id = _require_super_admin(request)
    original = await _get_case_or_404(sess, case_id)

    new_case = ModerationCase(
        kind=original.kind,
        subject_type=original.subject_type,
        subject_id=original.subject_id,
        subject_owner_user_id=original.subject_owner_user_id,
        reporter_user_id=original.reporter_user_id,
        status="open",
        priority_tier=original.priority_tier,
        sla_due_at=original.sla_due_at,
        forced_human=original.forced_human,
        forced_reason=original.forced_reason,
        parent_case_id=original.id,
        opened_at=datetime.now(tz=timezone.utc),
    )
    sess.add(new_case)
    await sess.commit()
    await sess.refresh(new_case)
    return {"new_case_id": str(new_case.id), "parent_case_id": str(case_id)}


# ---------------------------------------------------------------------------
# User-360 history
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/history", response_model=list[CaseSummary])
async def user_history(
    user_id: uuid.UUID,
    request: Request,
    limit: int = Query(100, le=500),
    sess: AsyncSession = Depends(get_db),
) -> list[CaseSummary]:
    _require_mod_role(request)
    result = await sess.execute(
        select(ModerationCase)
        .where(ModerationCase.subject_owner_user_id == user_id)
        .order_by(ModerationCase.opened_at.desc())
        .limit(limit)
    )
    cases = result.scalars().all()
    return [_case_to_summary(c) for c in cases]


# ---------------------------------------------------------------------------
# DMCA moderator actions
# ---------------------------------------------------------------------------


@router.post("/dmca/{dmca_id}/mark-defective")
async def mark_dmca_defective(
    dmca_id: uuid.UUID,
    reason: str,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> dict:
    """Moderator marks a DMCA notice as defective before hide_at fires."""
    _require_mod_role(request)
    from app.models import DMCANotice

    result = await sess.execute(select(DMCANotice).where(DMCANotice.id == dmca_id))
    notice = result.scalar_one_or_none()
    if not notice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DMCA notice not found")
    if notice.state != "received":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot mark defective from state '{notice.state}'")
    notice.state = "rejected_defective"
    notice.rejection_reason = reason
    await sess.commit()
    return {"dmca_id": str(dmca_id), "state": "rejected_defective"}


@router.post("/dmca/{dmca_id}/mark-suit-filed")
async def mark_suit_filed(
    dmca_id: uuid.UUID,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> dict:
    """Super-admin records that claimant has filed a court action — halts auto-restore."""
    _require_super_admin(request)
    from app.models import CounterNotice, DMCANotice

    result = await sess.execute(select(DMCANotice).where(DMCANotice.id == dmca_id))
    notice = result.scalar_one_or_none()
    if not notice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DMCA notice not found")

    if notice.counter_notice:
        notice.counter_notice.suit_filed_notice_received_at = datetime.now(tz=timezone.utc)
        notice.counter_notice.state = "permanent_taken_down"
    notice.state = "permanent"
    await sess.commit()
    return {"dmca_id": str(dmca_id), "state": "permanent"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_case_or_404(sess: AsyncSession, case_id: uuid.UUID) -> ModerationCase:
    result = await sess.execute(select(ModerationCase).where(ModerationCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _case_to_summary(c: ModerationCase) -> CaseSummary:
    return CaseSummary(
        id=c.id,
        kind=c.kind,
        subject_type=c.subject_type,
        subject_id=c.subject_id,
        subject_owner_user_id=c.subject_owner_user_id,
        score=float(c.score) if c.score is not None else None,
        forced_human=c.forced_human,
        forced_reason=c.forced_reason,
        status=c.status,
        priority_tier=c.priority_tier,
        sla_due_at=c.sla_due_at,
        sla_breached_at=c.sla_breached_at,
        opened_at=c.opened_at,
        claimed_by=c.claimed_by,
    )


def _case_to_detail(c: ModerationCase) -> CaseDetail:
    from app.schemas import ActionSummary

    actions = [
        ActionSummary(
            id=a.id,
            case_id=a.case_id,
            action_type=a.action_type,
            reviewer_id=a.reviewer_id,
            reason=a.reason,
            target_user_id=a.target_user_id,
            created_at=a.created_at,
            propagation_status=a.propagation_status,
        )
        for a in (c.actions or [])
    ]
    return CaseDetail(
        id=c.id,
        kind=c.kind,
        subject_type=c.subject_type,
        subject_id=c.subject_id,
        subject_owner_user_id=c.subject_owner_user_id,
        score=float(c.score) if c.score is not None else None,
        forced_human=c.forced_human,
        forced_reason=c.forced_reason,
        status=c.status,
        priority_tier=c.priority_tier,
        sla_due_at=c.sla_due_at,
        sla_breached_at=c.sla_breached_at,
        opened_at=c.opened_at,
        claimed_by=c.claimed_by,
        scores_breakdown=c.scores_breakdown or {},
        actions=actions,
    )
