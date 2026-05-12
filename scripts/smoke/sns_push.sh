#!/usr/bin/env bash
# smoke/sns_push.sh — Register a test device endpoint and publish a push notification.
# Usage: ENV=dev DEVICE_TOKEN=<apns-or-fcm-token> PLATFORM=apns bash scripts/smoke/sns_push.sh
# Requires: AWS CLI with SNS permissions.
set -euo pipefail

ENV="${ENV:-dev}"
REGION="${AWS_REGION:-us-east-1}"
PLATFORM="${PLATFORM:-apns}"      # apns or fcm
DEVICE_TOKEN="${DEVICE_TOKEN:-}"

if [[ -z "${DEVICE_TOKEN}" ]]; then
  echo "ERROR: DEVICE_TOKEN environment variable is required."
  echo "Usage: ENV=dev DEVICE_TOKEN=<token> PLATFORM=apns bash scripts/smoke/sns_push.sh"
  exit 1
fi

echo "==> SNS Mobile Push Smoke: env=${ENV}, platform=${PLATFORM}"

# Look up the platform application ARN
if [[ "${PLATFORM}" == "apns" ]]; then
  APP_NAME="colab-${ENV}-apns"
else
  APP_NAME="colab-${ENV}-fcm"
fi

PLATFORM_APP_ARN=$(aws sns list-platform-applications \
  --region "${REGION}" \
  --query "PlatformApplications[?contains(PlatformApplicationArn, '${APP_NAME}')].PlatformApplicationArn | [0]" \
  --output text 2>/dev/null || echo "")

if [[ -z "${PLATFORM_APP_ARN}" ]] || [[ "${PLATFORM_APP_ARN}" == "None" ]]; then
  echo "ERROR: Could not find SNS platform application for ${APP_NAME}."
  echo "       Ensure APNs/FCM credentials are seeded (scripts/seed_vendor_secrets.sh) and terraform applied."
  exit 1
fi

echo "    Platform App ARN: ${PLATFORM_APP_ARN}"

# Create platform endpoint
ENDPOINT_ARN=$(aws sns create-platform-endpoint \
  --region "${REGION}" \
  --platform-application-arn "${PLATFORM_APP_ARN}" \
  --token "${DEVICE_TOKEN}" \
  --attributes "Enabled=true" \
  --query 'EndpointArn' \
  --output text)

echo "    Endpoint ARN: ${ENDPOINT_ARN}"

# Publish test push notification
if [[ "${PLATFORM}" == "apns" ]]; then
  MESSAGE='{"APNS":"{\"aps\":{\"alert\":\"Colab smoke test push\",\"sound\":\"default\"}}","APNS_SANDBOX":"{\"aps\":{\"alert\":\"Colab smoke test push\",\"sound\":\"default\"}}"}'
else
  MESSAGE='{"GCM":"{\"notification\":{\"title\":\"Colab smoke test\",\"body\":\"Push notification smoke test\"}}"}'
fi

MESSAGE_ID=$(aws sns publish \
  --region "${REGION}" \
  --target-arn "${ENDPOINT_ARN}" \
  --message "${MESSAGE}" \
  --message-structure "json" \
  --query 'MessageId' \
  --output text)

echo "    Message ID: ${MESSAGE_ID}"
echo ""
echo "PASS: SNS push published. Message ID: ${MESSAGE_ID}"
echo "      Check the physical device (${PLATFORM}) for notification."

# Clean up test endpoint
echo "    Cleaning up test endpoint..."
aws sns delete-endpoint --region "${REGION}" --endpoint-arn "${ENDPOINT_ARN}"
echo "    Endpoint deleted."
