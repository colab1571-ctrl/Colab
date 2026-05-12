#!/usr/bin/env bash
# seed_vendor_secrets.sh — Idempotent script to seed vendor API keys into AWS Secrets Manager.
# Reads from local .env file and writes JSON blobs to the per-service secret paths.
# Usage: ENV=dev bash scripts/seed_vendor_secrets.sh
# Requires: aws CLI configured with sufficient Secrets Manager permissions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV="${ENV:-dev}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env file not found at ${ENV_FILE}"
  echo "Copy .env.example to .env and fill in values before running."
  exit 1
fi

# Load .env (ignore comments and empty lines)
set -o allexport
# shellcheck disable=SC1090
source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$')
set +o allexport

echo "==> Seeding vendor secrets for env=${ENV}"
echo "    Using: ${ENV_FILE}"
echo ""

# ── Helper: put_secret ─────────────────────────────────────────────────────────
put_secret() {
  local secret_name="$1"
  local secret_json="$2"

  echo -n "    Writing ${secret_name} ... "
  if aws secretsmanager describe-secret --secret-id "${secret_name}" &>/dev/null; then
    aws secretsmanager put-secret-value \
      --secret-id "${secret_name}" \
      --secret-string "${secret_json}" \
      --output text --query 'VersionId' | xargs -I{} echo "updated ({})"
  else
    echo "SKIP — secret does not exist (run terraform apply first)"
  fi
}

# ── auth-svc ──────────────────────────────────────────────────────────────────
AUTH_JSON=$(jq -n \
  --arg jwt_secret "${JWT_SECRET:-}" \
  --arg apple_team_id "${APPLE_TEAM_ID:-}" \
  --arg apple_bundle_id "${APPLE_BUNDLE_ID:-}" \
  --arg apple_key_id "${APPLE_KEY_ID:-}" \
  --arg apple_private_key "${APPLE_PRIVATE_KEY:-}" \
  --arg apple_sign_in_client_id "${APPLE_SIGN_IN_CLIENT_ID:-}" \
  --arg google_client_id_ios "${GOOGLE_CLIENT_ID_IOS:-}" \
  --arg google_client_id_android "${GOOGLE_CLIENT_ID_ANDROID:-}" \
  --arg google_client_id_web "${GOOGLE_CLIENT_ID_WEB:-}" \
  --arg google_client_secret_web "${GOOGLE_CLIENT_SECRET_WEB:-}" \
  --arg google_service_account_json "${GOOGLE_SERVICE_ACCOUNT_JSON:-}" \
  '{
    JWT_SECRET: $jwt_secret,
    APPLE_TEAM_ID: $apple_team_id,
    APPLE_BUNDLE_ID: $apple_bundle_id,
    APPLE_KEY_ID: $apple_key_id,
    APPLE_PRIVATE_KEY: $apple_private_key,
    APPLE_SIGN_IN_CLIENT_ID: $apple_sign_in_client_id,
    GOOGLE_CLIENT_ID_IOS: $google_client_id_ios,
    GOOGLE_CLIENT_ID_ANDROID: $google_client_id_android,
    GOOGLE_CLIENT_ID_WEB: $google_client_id_web,
    GOOGLE_CLIENT_SECRET_WEB: $google_client_secret_web,
    GOOGLE_SERVICE_ACCOUNT_JSON: $google_service_account_json
  }')
put_secret "colab/${ENV}/auth-svc/env" "${AUTH_JSON}"

# ── identity-svc ──────────────────────────────────────────────────────────────
IDENTITY_JSON=$(jq -n \
  --arg persona_api_key "${PERSONA_API_KEY:-}" \
  --arg persona_template_id "${PERSONA_TEMPLATE_ID:-}" \
  --arg persona_webhook_secret "${PERSONA_WEBHOOK_SECRET:-}" \
  '{
    PERSONA_API_KEY: $persona_api_key,
    PERSONA_TEMPLATE_ID: $persona_template_id,
    PERSONA_WEBHOOK_SECRET: $persona_webhook_secret
  }')
put_secret "colab/${ENV}/identity-svc/env" "${IDENTITY_JSON}"

# ── billing-svc ───────────────────────────────────────────────────────────────
BILLING_JSON=$(jq -n \
  --arg stripe_secret_key "${STRIPE_SECRET_KEY:-}" \
  --arg stripe_publishable_key "${STRIPE_PUBLISHABLE_KEY:-}" \
  --arg stripe_webhook_secret "${STRIPE_WEBHOOK_SECRET:-}" \
  --arg revenuecat_api_key_ios "${REVENUECAT_API_KEY_IOS:-}" \
  --arg revenuecat_api_key_android "${REVENUECAT_API_KEY_ANDROID:-}" \
  --arg revenuecat_secret_key "${REVENUECAT_SECRET_KEY:-}" \
  --arg revenuecat_webhook_secret "${REVENUECAT_WEBHOOK_SECRET:-}" \
  '{
    STRIPE_SECRET_KEY: $stripe_secret_key,
    STRIPE_PUBLISHABLE_KEY: $stripe_publishable_key,
    STRIPE_WEBHOOK_SECRET: $stripe_webhook_secret,
    REVENUECAT_API_KEY_IOS: $revenuecat_api_key_ios,
    REVENUECAT_API_KEY_ANDROID: $revenuecat_api_key_android,
    REVENUECAT_SECRET_KEY: $revenuecat_secret_key,
    REVENUECAT_WEBHOOK_SECRET: $revenuecat_webhook_secret
  }')
put_secret "colab/${ENV}/billing-svc/env" "${BILLING_JSON}"

# ── ai-orchestrator-svc ───────────────────────────────────────────────────────
AI_JSON=$(jq -n \
  --arg openai_api_key "${OPENAI_API_KEY:-}" \
  --arg openai_org_id "${OPENAI_ORG_ID:-}" \
  --arg replicate_api_token "${REPLICATE_API_TOKEN:-}" \
  --arg replicate_webhook_secret "${REPLICATE_WEBHOOK_SECRET:-}" \
  '{
    OPENAI_API_KEY: $openai_api_key,
    OPENAI_ORG_ID: $openai_org_id,
    REPLICATE_API_TOKEN: $replicate_api_token,
    REPLICATE_WEBHOOK_SECRET: $replicate_webhook_secret
  }')
put_secret "colab/${ENV}/ai-orchestrator-svc/env" "${AI_JSON}"

# ── meeting-svc ───────────────────────────────────────────────────────────────
MEETING_JSON=$(jq -n \
  --arg recall_api_token "${RECALL_API_TOKEN:-}" \
  --arg recall_webhook_secret "${RECALL_WEBHOOK_SECRET:-}" \
  --arg google_client_id_web "${GOOGLE_CLIENT_ID_WEB:-}" \
  --arg google_client_secret_web "${GOOGLE_CLIENT_SECRET_WEB:-}" \
  '{
    RECALL_API_TOKEN: $recall_api_token,
    RECALL_WEBHOOK_SECRET: $recall_webhook_secret,
    GOOGLE_CLIENT_ID_WEB: $google_client_id_web,
    GOOGLE_CLIENT_SECRET_WEB: $google_client_secret_web
  }')
put_secret "colab/${ENV}/meeting-svc/env" "${MEETING_JSON}"

# ── geo-svc ───────────────────────────────────────────────────────────────────
GEO_JSON=$(jq -n \
  --arg mapbox_secret_token "${MAPBOX_SECRET_TOKEN:-}" \
  '{MAPBOX_SECRET_TOKEN: $mapbox_secret_token}')
put_secret "colab/${ENV}/geo-svc/env" "${GEO_JSON}"

# ── profile-svc ───────────────────────────────────────────────────────────────
PROFILE_JSON=$(jq -n \
  --arg meta_app_id "${META_APP_ID:-}" \
  --arg meta_app_secret "${META_APP_SECRET:-}" \
  --arg spotify_client_id "${SPOTIFY_CLIENT_ID:-}" \
  --arg spotify_client_secret "${SPOTIFY_CLIENT_SECRET:-}" \
  --arg youtube_api_key "${YOUTUBE_API_KEY:-}" \
  '{
    META_APP_ID: $meta_app_id,
    META_APP_SECRET: $meta_app_secret,
    SPOTIFY_CLIENT_ID: $spotify_client_id,
    SPOTIFY_CLIENT_SECRET: $spotify_client_secret,
    YOUTUBE_API_KEY: $youtube_api_key
  }')
put_secret "colab/${ENV}/profile-svc/env" "${PROFILE_JSON}"

# ── Shared: apns (token-based) ────────────────────────────────────────────────
APNS_JSON=$(jq -n \
  --arg team_id "${APPLE_TEAM_ID:-}" \
  --arg key_id "${APPLE_KEY_ID:-}" \
  --arg bundle_id "${APPLE_BUNDLE_ID:-}" \
  --arg private_key "${APPLE_PRIVATE_KEY:-}" \
  '{team_id: $team_id, key_id: $key_id, bundle_id: $bundle_id, private_key: $private_key}')
put_secret "colab/${ENV}/shared/apns" "${APNS_JSON}"

# ── Shared: fcm ───────────────────────────────────────────────────────────────
FCM_JSON=$(jq -n \
  --arg server_key "${GOOGLE_SERVICE_ACCOUNT_JSON:-}" \
  '{server_key: $server_key}')
put_secret "colab/${ENV}/shared/fcm" "${FCM_JSON}"

# ── Shared: jwt ───────────────────────────────────────────────────────────────
JWT_JSON=$(jq -n \
  --arg jwt_secret "${JWT_SECRET:-}" \
  '{JWT_SECRET: $jwt_secret}')
put_secret "colab/${ENV}/shared/jwt" "${JWT_JSON}"

echo ""
echo "==> Done seeding vendor secrets for env=${ENV}."
echo "    Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
