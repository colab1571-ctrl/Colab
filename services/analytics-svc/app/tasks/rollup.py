"""
analytics-svc — Nightly KPI rollup Celery tasks.

Computes all 7 master §6 metrics for a given day and upserts into KPIRollup.
Each metric runs in its own try/except so one failure doesn't abort others.

Metrics:
  1. onboarding_completion   — funnel completion rate per step
  2. dau_split               — DAU split new vs existing
  3. profile_health_dist     — profile health score distribution
  4. request_ratio           — collab invite outcome counts
  5. collab_feedback         — up/down vote counts per axis
  6. support_csat            — avg CSAT per ticket category
  7. pct_reported            — % of DAU that received a report
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import sentry_sdk
from sqlalchemy import text

from app.config import get_settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_sync_engine():
    """Create a synchronous SQLAlchemy engine for Celery tasks (not async)."""
    from sqlalchemy import create_engine
    settings = get_settings()
    return create_engine(settings.database_url_sync, pool_pre_ping=True)


def _upsert_rollup(conn, day: date, key: str, dims: dict, value: Any, count_n: int | None) -> None:
    """Upsert a KPIRollup row. ON CONFLICT DO UPDATE for idempotent backfill."""
    dims_json = json.dumps(dims, sort_keys=True)
    conn.execute(
        text("""
            INSERT INTO analytics.kpi_rollup (id, day, key, dims, value, count_n, updated_at)
            VALUES (gen_random_uuid(), :day, :key, :dims::jsonb, :value, :count_n, now())
            ON CONFLICT ON CONSTRAINT uq_kpi_rollup_day_key_dims
            DO UPDATE SET value = EXCLUDED.value, count_n = EXCLUDED.count_n, updated_at = now()
        """),
        {"day": day, "key": key, "dims": dims_json, "value": value, "count_n": count_n},
    )


def _run_onboarding_completion(conn, day: date) -> None:
    """
    Funnel completion rate per onboarding step.

    SQL from plan §10.1 — computes ratio of users who reached each step
    relative to users who started (signed up) on :day.
    """
    rows = conn.execute(
        text("""
            WITH funnels AS (
              SELECT user_id,
                     MIN(CASE WHEN event = 'signup'           THEN ts END) AS t_signup,
                     MIN(CASE WHEN event = 'verify_email'     THEN ts END) AS t_verify_email,
                     MIN(CASE WHEN event = 'age_attest'       THEN ts END) AS t_age_attest,
                     MIN(CASE WHEN event = 'profile_basic'    THEN ts END) AS t_profile_basic,
                     MIN(CASE WHEN event = 'portfolio_done'   THEN ts END) AS t_portfolio,
                     MIN(CASE WHEN event = 'selfie_done'      THEN ts END) AS t_selfie,
                     MIN(CASE WHEN event = 'badge_issued'     THEN ts END) AS t_badge
              FROM analytics.events
              WHERE ts::date = :day
              GROUP BY user_id
            )
            SELECT step,
                   count(*) FILTER (WHERE col IS NOT NULL)::numeric / NULLIF(count(*), 0) AS value,
                   count(*) AS count_n
            FROM funnels f,
                 LATERAL (VALUES
                   ('signup',       f.t_signup),
                   ('verify_email', f.t_verify_email),
                   ('age_attest',   f.t_age_attest),
                   ('profile_basic',f.t_profile_basic),
                   ('portfolio',    f.t_portfolio),
                   ('selfie',       f.t_selfie),
                   ('badge',        f.t_badge)
                 ) AS s(step, col)
            GROUP BY step
        """),
        {"day": day},
    )
    for row in rows:
        _upsert_rollup(
            conn, day,
            key="onboarding_completion",
            dims={"step": row.step},
            value=float(row.value) if row.value is not None else None,
            count_n=row.count_n,
        )


def _run_dau_split(conn, day: date) -> None:
    """DAU split: new vs existing users. SQL from plan §10.2."""
    rows = conn.execute(
        text("""
            WITH actives AS (
              SELECT DISTINCT user_id
              FROM analytics.events
              WHERE ts::date = :day AND event = 'app_active'
            ),
            ages AS (
              SELECT u.id AS user_id,
                     CASE WHEN u.created_at::date = :day THEN 'new' ELSE 'existing' END AS segment
              FROM auth.user u
              JOIN actives a ON a.user_id = u.id
            )
            SELECT segment,
                   count(*)::numeric AS value,
                   count(*) AS count_n
            FROM ages
            GROUP BY segment
        """),
        {"day": day},
    )
    for row in rows:
        _upsert_rollup(
            conn, day,
            key="dau_split",
            dims={"segment": row.segment},
            value=float(row.value),
            count_n=row.count_n,
        )


def _run_profile_health_dist(conn, day: date) -> None:
    """Profile health score distribution in 5 buckets. SQL from plan §10.3."""
    bucket_labels = {1: "0.0-0.2", 2: "0.2-0.4", 3: "0.4-0.6", 4: "0.6-0.8", 5: "0.8-1.0"}
    rows = conn.execute(
        text("""
            SELECT width_bucket(profile_health_score, 0, 1, 5) AS bucket,
                   count(*)::numeric AS value,
                   count(*) AS count_n
            FROM profile.profile
            WHERE updated_at::date <= :day
              AND profile_health_score IS NOT NULL
            GROUP BY 1
        """),
        {"day": day},
    )
    for row in rows:
        label = bucket_labels.get(row.bucket, f"bucket_{row.bucket}")
        _upsert_rollup(
            conn, day,
            key="profile_health_dist",
            dims={"bucket": label},
            value=float(row.value),
            count_n=row.count_n,
        )


def _run_request_ratio(conn, day: date) -> None:
    """Collab invite outcome counts. SQL from plan §10.4."""
    rows = conn.execute(
        text("""
            SELECT status,
                   count(*)::numeric AS value,
                   count(*) AS count_n
            FROM invite.collab_invite
            WHERE created_at::date = :day
            GROUP BY status
        """),
        {"day": day},
    )
    for row in rows:
        _upsert_rollup(
            conn, day,
            key="request_ratio",
            dims={"outcome": row.status},
            value=float(row.value),
            count_n=row.count_n,
        )


def _run_collab_feedback(conn, day: date) -> None:
    """Collab feedback up/down vote counts. SQL from plan §10.5."""
    rows = conn.execute(
        text("""
            SELECT axis, direction,
                   count(*)::numeric AS value,
                   count(*) AS count_n
            FROM collab.feedback
            WHERE created_at::date = :day
            GROUP BY axis, direction
        """),
        {"day": day},
    )
    for row in rows:
        _upsert_rollup(
            conn, day,
            key="collab_feedback",
            dims={"axis": row.axis, "direction": row.direction},
            value=float(row.value),
            count_n=row.count_n,
        )


def _run_support_csat(conn, day: date) -> None:
    """Average support CSAT per ticket category. SQL from plan §10.6."""
    rows = conn.execute(
        text("""
            SELECT t.category,
                   avg(c.score)::numeric AS value,
                   count(*) AS count_n
            FROM support.csat c
            JOIN support.ticket t ON t.id = c.ticket_id
            WHERE c.created_at::date = :day
            GROUP BY t.category
        """),
        {"day": day},
    )
    for row in rows:
        _upsert_rollup(
            conn, day,
            key="support_csat",
            dims={"category": row.category},
            value=float(row.value) if row.value is not None else None,
            count_n=row.count_n,
        )


def _run_pct_reported(conn, day: date) -> None:
    """% of DAU that received a profile report. SQL from plan §10.7."""
    row = conn.execute(
        text("""
            WITH reported AS (
              SELECT DISTINCT subject_id AS user_id
              FROM moderation.report
              WHERE created_at::date = :day AND subject_type = 'profile'
            ),
            dau AS (
              SELECT count(DISTINCT user_id) AS n
              FROM analytics.events
              WHERE ts::date = :day AND event = 'app_active'
            )
            SELECT (SELECT count(*) FROM reported)::numeric AS reported_n,
                   (SELECT n FROM dau) AS dau_n
        """),
        {"day": day},
    )
    row = row.one()
    dau_n = int(row.dau_n) if row.dau_n else 0
    reported_n = int(row.reported_n) if row.reported_n else 0
    value = reported_n / dau_n if dau_n > 0 else None
    _upsert_rollup(
        conn, day,
        key="pct_reported",
        dims={},
        value=value,
        count_n=dau_n,
    )


def rollup_day(day: date) -> dict[str, str]:
    """
    Run all 7 KPI queries for the given day.

    Each query is wrapped in try/except so one failure logs but doesn't
    abort the rest. Returns a status dict.
    """
    engine = _get_sync_engine()
    status: dict[str, str] = {}

    metrics = [
        ("onboarding_completion", _run_onboarding_completion),
        ("dau_split", _run_dau_split),
        ("profile_health_dist", _run_profile_health_dist),
        ("request_ratio", _run_request_ratio),
        ("collab_feedback", _run_collab_feedback),
        ("support_csat", _run_support_csat),
        ("pct_reported", _run_pct_reported),
    ]

    with engine.begin() as conn:
        for key, fn in metrics:
            try:
                fn(conn, day)
                status[key] = "ok"
                logger.info("KPI rollup ok", extra={"metric": key, "day": str(day)})
            except Exception as exc:
                status[key] = f"error: {exc}"
                logger.exception("KPI rollup failed", extra={"metric": key, "day": str(day)})
                try:
                    sentry_sdk.capture_exception(exc)
                except Exception:
                    pass

    return status


@celery_app.task(name="app.tasks.rollup.rollup_yesterday", bind=True, max_retries=3)
def rollup_yesterday(self) -> dict:
    """Celery Beat task: compute KPI rollups for yesterday (02:00 UTC)."""
    yesterday = date.today() - timedelta(days=1)
    logger.info("Starting nightly KPI rollup", extra={"day": str(yesterday)})
    result = rollup_day(yesterday)
    failed = {k: v for k, v in result.items() if not v.startswith("ok")}
    if failed:
        logger.error("Some KPI metrics failed", extra={"failed": failed})
    return {"day": str(yesterday), "metrics": result}


@celery_app.task(name="app.tasks.rollup.backfill", bind=True)
def backfill(self, from_date: str, to_date: str) -> dict:
    """
    Backfill KPI rollups for a date range.

    Usage: celery call app.tasks.rollup.backfill --args '["2026-01-01","2026-02-01"]'
    Or CLI: python -m analytics.rollup --backfill 2026-01-01..2026-02-01
    """
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    results: dict[str, dict] = {}

    current = start
    while current <= end:
        logger.info("Backfilling KPI rollup", extra={"day": str(current)})
        results[str(current)] = rollup_day(current)
        current += timedelta(days=1)

    return results
