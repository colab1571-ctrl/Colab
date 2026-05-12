"""
auth-svc — Transactional email via AWS SES.

Templates are loaded from the templates/email/ directory.
In dev, emails are logged only (SES_ENABLED=false).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


async def send_email_verification(email: str, token: str, otp: str, app_domain: str) -> None:
    """Send verification email with magic-link + OTP fallback."""
    link = f"https://{app_domain}/auth/verify?t={token}"
    body = (
        f"Verify your Colab account.\n\n"
        f"Click the link: {link}\n\n"
        f"Or enter this 6-digit code in the app: {otp}\n\n"
        f"Link expires in 15 minutes. Do not share this code."
    )
    await _send(to=email, subject="Verify your Colab account", body=body)


async def send_password_reset(email: str, token: str, otp: str, app_domain: str) -> None:
    """Send password reset email with magic-link + OTP fallback."""
    link = f"https://{app_domain}/auth/reset-password?t={token}"
    body = (
        f"Reset your Colab password.\n\n"
        f"Click the link: {link}\n\n"
        f"Or enter this code in the app: {otp}\n\n"
        f"Link expires in 15 minutes. If you did not request this, ignore this email."
    )
    await _send(to=email, subject="Reset your Colab password", body=body)


async def send_email_change_verification(new_email: str, token: str, otp: str, app_domain: str) -> None:
    """Send verification email to the new address for email change flow."""
    link = f"https://{app_domain}/auth/change-email?t={token}"
    body = (
        f"Confirm your new Colab email address.\n\n"
        f"Click the link: {link}\n\n"
        f"Or enter this code in the app: {otp}\n\n"
        f"Link expires in 15 minutes."
    )
    await _send(to=new_email, subject="Confirm your new Colab email address", body=body)


async def _send(to: str, subject: str, body: str) -> None:
    """Send via SES (or log in dev mode)."""
    ses_enabled = os.environ.get("SES_ENABLED", "false").lower() == "true"
    from_address = os.environ.get("SES_FROM_ADDRESS", "no-reply@colab.com")
    region = os.environ.get("AWS_REGION", "us-east-1")

    if not ses_enabled:
        logger.info("DEV: email suppressed", extra={"to": to, "subject": subject, "body_preview": body[:80]})
        return

    import boto3

    client = boto3.client("ses", region_name=region)
    client.send_email(
        Source=from_address,
        Destination={"ToAddresses": [to]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
        ReplyToAddresses=[os.environ.get("SES_REPLY_TO", "support@colab.com")],
    )
    logger.info("Email sent via SES", extra={"to": to, "subject": subject})
