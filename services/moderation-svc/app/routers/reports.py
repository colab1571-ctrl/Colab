"""
moderation-svc — Report intake router.
POST /reports — M-020, M-021, M-022
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import ModerationCase, Report, ReportThrottle
from app.schemas import ReportCreate, ReportResponse
from app.config import get_mod_settings

router = APIRouter(prefix="/reports", tags=["reports"])


async def _get_reporter_user_id(request: Request) -> uuid.UUID:
    """Extract authenticated user ID from JWT claims (set by gateway middleware)."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        return uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identity")


async def _check_and_increment_throttle(
    sess: AsyncSession,
    reporter_user_id: uuid.UUID,
    limit: int,
) -> None:
    """
    Enforce per-reporter daily report limit (M-021).
    Uses ReportThrottle table keyed by (user_id, day).
    """
    from sqlalchemy import func, select, update

    today = datetime.now(tz=timezone.utc).date()
    today_ts = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    result = await sess.execute(
        select(ReportThrottle).where(
            ReportThrottle.reporter_user_id == reporter_user_id,
            ReportThrottle.day == today_ts,
        )
    )
    throttle = result.scalar_one_or_none()

    if throttle is None:
        throttle = ReportThrottle(
            reporter_user_id=reporter_user_id, day=today_ts, count=1
        )
        sess.add(throttle)
    else:
        if throttle.count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Report limit of {limit}/day exceeded. Try again tomorrow.",
                headers={"Retry-After": "86400"},
            )
        throttle.count += 1


async def _find_or_create_case(
    sess: AsyncSession,
    subject_type: str,
    subject_id: uuid.UUID,
    reporter_user_id: uuid.UUID,
) -> ModerationCase:
    """
    De-dup reports against same subject (plan §11.5):
    Collapse all reports about the same subject into a single open case.
    """
    from sqlalchemy import select

    result = await sess.execute(
        select(ModerationCase).where(
            ModerationCase.subject_type == subject_type,
            ModerationCase.subject_id == subject_id,
            ModerationCase.status == "open",
            ModerationCase.kind == "report",
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Create new case
    from datetime import timedelta
    from app.config import get_mod_settings

    settings = get_mod_settings()
    now = datetime.now(tz=timezone.utc)
    sla_due = now + timedelta(hours=settings.tier1_sla_hours)  # default tier_1 for manual reports

    case = ModerationCase(
        kind="report",
        subject_type=subject_type,
        subject_id=subject_id,
        subject_owner_user_id=subject_id,  # approximation; caller should pass owner
        reporter_user_id=reporter_user_id,
        status="open",
        priority_tier="tier_1_24h",
        sla_due_at=sla_due,
        opened_at=now,
    )
    sess.add(case)
    await sess.flush()
    return case


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ReportResponse)
async def create_report(
    body: ReportCreate,
    request: Request,
    sess: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """
    File a user report against a piece of content or a user.

    Rate-limited: 20 reports/user/day (admin-tunable via MOD_REPORTS_PER_USER_PER_DAY).
    De-duplicated: multiple reports about the same subject collapse into one ModerationCase.
    """
    settings = get_mod_settings()
    reporter_id = await _get_reporter_user_id(request)

    # Rate-limit check
    await _check_and_increment_throttle(sess, reporter_id, settings.reports_per_user_per_day)

    # Detect coordinated attack (>=5 reports of same subject from distinct accounts in 10 min)
    # and emit an alert (best effort, non-blocking)
    from sqlalchemy import func, select
    from datetime import timedelta

    now = datetime.now(tz=timezone.utc)
    ten_min_ago = now - timedelta(minutes=10)
    recent_reporter_count_result = await sess.execute(
        select(func.count(Report.reporter_user_id.distinct())).where(
            Report.subject_type == body.subject_type,
            Report.subject_id == body.subject_id,
            Report.created_at >= ten_min_ago,
        )
    )
    recent_reporter_count = recent_reporter_count_result.scalar_one() or 0
    if recent_reporter_count >= 4:  # 5th reporter triggers alert
        # Best-effort alert — don't fail the request
        from app.workers.sla_tasks import _emit_sync
        try:
            _emit_sync(
                "moderation.coordinated_attack_suspected",
                {
                    "subject_type": body.subject_type,
                    "subject_id": str(body.subject_id),
                    "reporter_count": recent_reporter_count + 1,
                },
            )
        except Exception:
            pass

    # Find or create case (de-dup by subject)
    case = await _find_or_create_case(
        sess, body.subject_type, body.subject_id, reporter_id
    )

    # Insert Report row
    report = Report(
        reporter_user_id=reporter_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        description=body.description,
        screenshot_s3_key=body.screenshot_s3_key,
        case_id=case.id,
        reporter_ip=request.client.host if request.client else None,
        device_id=request.headers.get("X-Device-Id"),
    )
    sess.add(report)
    await sess.commit()
    await sess.refresh(report)

    # Emit event (outbox / direct)
    from colab_common.events import publish
    try:
        await publish(
            "moderation.report_filed",
            {
                "report_id": str(report.id),
                "case_id": str(case.id),
                "subject_type": body.subject_type,
                "subject_id": str(body.subject_id),
                "reporter_user_id": str(reporter_id),
            },
        )
    except Exception:
        pass  # event publish failure is non-fatal

    return ReportResponse(
        report_id=report.id,
        case_id=case.id,
        created_at=report.created_at,
        status="open",
    )
