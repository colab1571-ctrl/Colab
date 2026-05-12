"""gateway-svc configuration."""
from __future__ import annotations

import os

from colab_common.settings import get_settings

settings = get_settings()

SERVICE_NAME = "gateway-svc"
GIT_SHA = os.environ.get("GIT_SHA", "dev")
IMAGE_TAG = os.environ.get("IMAGE_TAG", "dev")

# Upstream service URLs (override via env in production; Kubernetes service DNS)
UPSTREAM_URLS: dict[str, str] = {
    "auth":         os.environ.get("UPSTREAM_AUTH_URL",         "http://auth-svc:8000"),
    "profile":      os.environ.get("UPSTREAM_PROFILE_URL",      "http://profile-svc:8000"),
    "identity":     os.environ.get("UPSTREAM_IDENTITY_URL",     "http://identity-svc:8000"),
    "discovery":    os.environ.get("UPSTREAM_DISCOVERY_URL",    "http://discovery-svc:8000"),
    "matching":     os.environ.get("UPSTREAM_MATCHING_URL",     "http://matching-svc:8000"),
    "invite":       os.environ.get("UPSTREAM_INVITE_URL",       "http://invite-svc:8000"),
    "collab":       os.environ.get("UPSTREAM_COLLAB_URL",       "http://collab-svc:8000"),
    "chat":         os.environ.get("UPSTREAM_CHAT_URL",         "http://chat-svc:8000"),
    "media":        os.environ.get("UPSTREAM_MEDIA_URL",        "http://media-svc:8000"),
    "ai":           os.environ.get("UPSTREAM_AI_URL",           "http://ai-orchestrator-svc:8000"),
    "moderation":   os.environ.get("UPSTREAM_MODERATION_URL",   "http://moderation-svc:8000"),
    "notification": os.environ.get("UPSTREAM_NOTIFICATION_URL", "http://notification-svc:8000"),
    "billing":      os.environ.get("UPSTREAM_BILLING_URL",      "http://billing-svc:8000"),
    "support":      os.environ.get("UPSTREAM_SUPPORT_URL",      "http://support-svc:8000"),
    "admin":        os.environ.get("UPSTREAM_ADMIN_URL",        "http://admin-svc:8000"),
    "geo":          os.environ.get("UPSTREAM_GEO_URL",          "http://geo-svc:8000"),
    "meeting":      os.environ.get("UPSTREAM_MEETING_URL",      "http://meeting-svc:8000"),
    "analytics":    os.environ.get("UPSTREAM_ANALYTICS_URL",    "http://analytics-svc:8000"),
    # P1 test service
    "hello":        os.environ.get("UPSTREAM_HELLO_URL",        "http://hello-svc:8000"),
}
