"""
Email channel — AWS SES + Jinja2-rendered MJML-compiled HTML templates.

Template files live in templates/email/*.html (compiled from *.mjml at build time).
Jinja2 renders context variables into the compiled HTML.

Transactional override: send_transactional_email() skips all preference checks.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import boto3
import html2text
from botocore.exceptions import ClientError
from jinja2 import Environment, FileSystemLoader, select_autoescape

from colab_common.settings import get_settings

logger = logging.getLogger(__name__)

_ses_client: Any = None
_jinja_env: Environment | None = None

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "email"

NOREPLY_ADDRESS = os.environ.get("SES_NOREPLY_FROM", "noreply@mail.colab.app")
MARKETING_ADDRESS = os.environ.get("SES_MARKETING_FROM", "hello@mail.colab.app")
SES_CONFIGURATION_SET = os.environ.get("SES_CONFIGURATION_SET", "colab-notifications")


def _get_ses() -> Any:
    global _ses_client
    if _ses_client is None:
        settings = get_settings()
        _ses_client = boto3.client("ses", region_name=settings.aws_region)
    return _ses_client


def _get_jinja() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
    return _jinja_env


def render_template(template_name: str, context: dict[str, Any]) -> tuple[str, str]:
    """
    Render an email template.
    Returns (html_body, text_body).
    """
    jinja = _get_jinja()
    try:
        tmpl = jinja.get_template(template_name)
        html_body = tmpl.render(**context)
    except Exception as exc:
        logger.error("Failed to render template %s: %s", template_name, exc)
        # Fallback to plain text
        html_body = f"<p>{context.get('subject', '')}</p>"

    h = html2text.HTML2Text()
    h.ignore_links = False
    text_body = h.handle(html_body)
    return html_body, text_body


def send_email(
    to_address: str,
    subject: str,
    template_name: str,
    context: dict[str, Any],
    *,
    from_address: str = NOREPLY_ADDRESS,
    list_unsubscribe_header: str | None = None,
    list_unsubscribe_post_header: str | None = None,
) -> bool:
    """
    Send a notification email via SES.
    Returns True on success, False on failure.
    """
    html_body, text_body = render_template(template_name, {**context, "subject": subject})

    ses = _get_ses()

    try:
        kwargs: dict[str, Any] = {
            "Source": from_address,
            "Destination": {"ToAddresses": [to_address]},
            "Message": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                    "Text": {"Data": text_body, "Charset": "UTF-8"},
                },
            },
        }
        if SES_CONFIGURATION_SET:
            kwargs["ConfigurationSetName"] = SES_CONFIGURATION_SET

        # RFC 8058 List-Unsubscribe headers
        headers = []
        if list_unsubscribe_header:
            headers.append({"Name": "List-Unsubscribe", "Value": list_unsubscribe_header})
        if list_unsubscribe_post_header:
            headers.append({"Name": "List-Unsubscribe-Post", "Value": list_unsubscribe_post_header})
        # Note: SES SendEmail does not support custom headers directly;
        # use SendRawEmail for List-Unsubscribe. Stub for now.

        ses.send_email(**kwargs)
        logger.info("Email sent", extra={"to": to_address, "subject": subject, "template": template_name})
        return True
    except ClientError as exc:
        logger.error("SES send_email failed: %s", exc, exc_info=True)
        return False


def send_transactional_email(
    to_address: str,
    subject: str,
    template_name: str,
    context: dict[str, Any],
) -> bool:
    """
    Send a transactional email that bypasses all preference checks.
    Used by auth-svc, billing-svc, moderation-svc via shared library.
    """
    return send_email(to_address, subject, template_name, context)
