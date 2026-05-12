"""
ICS file generator for meeting-svc.

Generates RFC 5545-compliant .ics files for Google Meet events.
Uses the `icalendar` library. Uploads to S3 and returns the S3 key.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


def generate_ics(
    *,
    meeting_id: uuid.UUID,
    summary: str,
    description: str,
    start_dt: datetime,
    duration_min: int,
    join_url: str,
    organizer_email: str = "noreply@colab.app",
) -> bytes:
    """
    Generate an RFC 5545 .ics file for the given meeting.

    Returns raw bytes suitable for S3 upload.
    """
    try:
        from icalendar import Calendar, Event, vDatetime, vText, vUri
    except ImportError:
        raise RuntimeError("icalendar package is required. Install: pip install icalendar")

    end_dt = start_dt + timedelta(minutes=duration_min)

    cal = Calendar()
    cal.add("prodid", "-//Colab//Meeting Scheduler//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "REQUEST")

    event = Event()
    event.add("uid", f"{meeting_id}@colab.app")
    event.add("summary", summary)
    event.add("description", description)
    event.add("dtstart", start_dt.replace(tzinfo=UTC))
    event.add("dtend", end_dt.replace(tzinfo=UTC))
    event.add("dtstamp", datetime.now(UTC))
    event.add("location", join_url)
    event.add("url", join_url)
    event.add("organizer", f"mailto:{organizer_email}")
    event.add("status", "CONFIRMED")
    event.add("transp", "OPAQUE")

    cal.add_component(event)
    return cal.to_ical()


async def upload_ics_to_s3(
    *,
    meeting_id: uuid.UUID,
    ics_bytes: bytes,
    s3_bucket: str,
    s3_region: str,
) -> str:
    """
    Upload an ICS file to S3.

    Returns the S3 key (not a signed URL — caller generates signed URL separately).
    """
    import boto3

    s3_key = f"artifacts/meetings/{meeting_id}/invite.ics"

    try:
        s3 = boto3.client("s3", region_name=s3_region)
        s3.put_object(
            Bucket=s3_bucket,
            Key=s3_key,
            Body=ics_bytes,
            ContentType="text/calendar; charset=utf-8",
            ContentDisposition=f'attachment; filename="colab-meeting-{meeting_id}.ics"',
        )
        logger.info("Uploaded ICS to s3://%s/%s", s3_bucket, s3_key)
        return s3_key
    except Exception as exc:
        logger.warning("Failed to upload ICS to S3: %s", exc)
        raise


def generate_signed_url(
    *,
    s3_key: str,
    s3_bucket: str,
    s3_region: str,
    ttl_seconds: int = 3600,
) -> str:
    """Generate a pre-signed S3 URL for downloading an artifact."""
    import boto3

    s3 = boto3.client("s3", region_name=s3_region)
    url: str = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": s3_bucket, "Key": s3_key},
        ExpiresIn=ttl_seconds,
    )
    return url
