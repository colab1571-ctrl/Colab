"""
Push channel — AWS SNS Mobile Push (APNs + FCM) with Expo fallback for dev.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import UUID

import boto3
from botocore.exceptions import ClientError

from colab_common.settings import get_settings

logger = logging.getLogger(__name__)

_sns_client: Any = None


def _get_sns() -> Any:
    global _sns_client
    if _sns_client is None:
        settings = get_settings()
        _sns_client = boto3.client("sns", region_name=settings.aws_region)
    return _sns_client


def _platform_arn(platform: str) -> str:
    """Retrieve the SNS platform application ARN from env/secrets."""
    if platform == "ios":
        return os.environ.get("SNS_APNS_PLATFORM_ARN", "")
    return os.environ.get("SNS_FCM_PLATFORM_ARN", "")


def create_or_update_sns_endpoint(device_token: str, platform: str, user_id: str) -> str | None:
    """
    Create (or re-enable) an SNS platform endpoint for a device.
    Returns the endpoint ARN or None on failure.
    """
    platform_arn = _platform_arn(platform)
    if not platform_arn:
        logger.warning("SNS platform ARN not configured for platform=%s", platform)
        return None

    sns = _get_sns()
    try:
        resp = sns.create_platform_endpoint(
            PlatformApplicationArn=platform_arn,
            Token=device_token,
            CustomUserData=str(user_id),
        )
        endpoint_arn: str = resp["EndpointArn"]
        logger.info("SNS endpoint created/found", extra={"endpoint_arn": endpoint_arn})
        return endpoint_arn
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "InvalidParameter":
            # Token may already be registered; try to find existing endpoint
            msg = exc.response["Error"]["Message"]
            logger.warning("SNS InvalidParameter: %s", msg)
            # Extract existing ARN from message if present
            if "Endpoint" in msg and "already exists" in msg:
                # AWS embeds the ARN in the error message
                parts = msg.split("arn:aws:sns:")
                if len(parts) > 1:
                    arn = "arn:aws:sns:" + parts[1].strip().rstrip(".")
                    # Re-enable endpoint with new token
                    try:
                        sns.set_endpoint_attributes(
                            EndpointArn=arn,
                            Attributes={"Enabled": "true", "Token": device_token},
                        )
                        return arn
                    except ClientError:
                        pass
        logger.error("Failed to create SNS endpoint", exc_info=True)
        return None


def delete_sns_endpoint(endpoint_arn: str) -> None:
    """Delete an SNS endpoint (called on device deregister)."""
    try:
        _get_sns().delete_endpoint(EndpointArn=endpoint_arn)
        logger.info("SNS endpoint deleted", extra={"endpoint_arn": endpoint_arn})
    except ClientError:
        logger.warning("Failed to delete SNS endpoint %s", endpoint_arn, exc_info=True)


def build_apns_payload(title: str, body: str, notif_id: str, notif_type: str, deep_link: str | None = None) -> dict[str, Any]:
    aps: dict[str, Any] = {
        "alert": {"title": title, "body": body},
        "sound": "default",
        "mutable-content": 1,
    }
    payload: dict[str, Any] = {"aps": aps, "notif_id": notif_id, "type": notif_type}
    if deep_link:
        payload["deep_link"] = deep_link
    return payload


def build_fcm_payload(title: str, body: str, notif_id: str, notif_type: str) -> dict[str, Any]:
    return {
        "message": {
            "notification": {"title": title, "body": body},
            "data": {"notif_id": notif_id, "type": notif_type},
            "android": {"priority": "high"},
        }
    }


def send_push(
    endpoint_arn: str,
    platform: str,
    title: str,
    body: str,
    notif_id: str,
    notif_type: str,
    deep_link: str | None = None,
) -> bool:
    """
    Publish a push notification via SNS to a specific endpoint.
    Returns True on success, raises on failure.
    Caller should catch ClientError with code EndpointDisabled.
    """
    apns_payload = build_apns_payload(title, body, notif_id, notif_type, deep_link)
    fcm_payload = build_fcm_payload(title, body, notif_id, notif_type)

    message = json.dumps(
        {
            "APNS": json.dumps(apns_payload),
            "APNS_SANDBOX": json.dumps(apns_payload),
            "GCM": json.dumps(fcm_payload),
            "default": body,
        }
    )

    sns = _get_sns()
    try:
        sns.publish(
            TargetArn=endpoint_arn,
            MessageStructure="json",
            Message=message,
        )
        logger.info("Push sent", extra={"endpoint_arn": endpoint_arn, "type": notif_type})
        return True
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        logger.warning("SNS publish failed: %s", code, exc_info=True)
        raise
