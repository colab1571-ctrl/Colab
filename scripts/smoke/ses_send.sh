#!/usr/bin/env bash
# smoke/ses_send.sh — Send a test email via SES and verify it was accepted.
# Usage: ENV=dev TO_EMAIL=you@example.com bash scripts/smoke/ses_send.sh
# Requires: AWS CLI with SES permissions.
set -euo pipefail

ENV="${ENV:-dev}"
REGION="${AWS_REGION:-us-east-1}"
FROM_EMAIL="${FROM_EMAIL:-}"
TO_EMAIL="${TO_EMAIL:-}"

if [[ -z "${TO_EMAIL}" ]]; then
  echo "ERROR: TO_EMAIL environment variable is required."
  echo "Usage: ENV=dev TO_EMAIL=you@example.com bash scripts/smoke/ses_send.sh"
  exit 1
fi

# Get the configuration set name
CONFIG_SET="colab-${ENV}"

echo "==> SES Smoke: env=${ENV}, region=${REGION}"
echo "    To: ${TO_EMAIL}"
echo "    Config Set: ${CONFIG_SET}"

# Get SES identity ARN to derive the from address
if [[ -z "${FROM_EMAIL}" ]]; then
  FROM_IDENTITY=$(aws sesv2 list-email-identities --region "${REGION}" \
    --query "EmailIdentities[?IdentityType=='DOMAIN'].IdentityName | [0]" \
    --output text 2>/dev/null || echo "")
  if [[ -n "${FROM_IDENTITY}" ]]; then
    FROM_EMAIL="smoke-test@${FROM_IDENTITY}"
  else
    echo "ERROR: Could not determine FROM_EMAIL. Set FROM_EMAIL env var."
    exit 1
  fi
fi

echo "    From: ${FROM_EMAIL}"

# Send test email
MESSAGE_ID=$(aws sesv2 send-email \
  --region "${REGION}" \
  --from-email-address "${FROM_EMAIL}" \
  --destination "ToAddresses=${TO_EMAIL}" \
  --content "Simple={Subject={Data='[Colab Smoke Test] SES verification ${ENV}',Charset=UTF-8},Body={Text={Data='This is an automated smoke test email from the Colab ${ENV} environment. DKIM should pass. Sent at: $(date -u)',Charset=UTF-8}}}" \
  --configuration-set-name "${CONFIG_SET}" \
  --query 'MessageId' \
  --output text)

echo "    Message ID: ${MESSAGE_ID}"
echo ""
echo "PASS: Email accepted by SES. Message ID: ${MESSAGE_ID}"
echo "      Check ${TO_EMAIL} inbox and verify DKIM pass."
echo "      For full DKIM scoring, use https://mail-tester.com and aim for >= 9/10."
