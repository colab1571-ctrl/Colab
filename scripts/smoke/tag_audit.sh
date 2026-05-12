#!/usr/bin/env bash
# smoke/tag_audit.sh — Verify all Colab resources are tagged with Project=colab.
# Usage: ENV=dev bash scripts/smoke/tag_audit.sh
# Requires: AWS CLI with resourcegroupstaggingapi permissions.
set -euo pipefail

ENV="${ENV:-dev}"
REGION="${AWS_REGION:-us-east-1}"

echo "==> Tag Audit Smoke: env=${ENV}, region=${REGION}"
echo "    Querying all resources tagged Project=colab, Env=${ENV} ..."

RESOURCES=$(aws resourcegroupstaggingapi get-resources \
  --region "${REGION}" \
  --tag-filters \
    "Key=Project,Values=colab" \
    "Key=Env,Values=${ENV}" \
  --query 'ResourceTagMappingList[].ResourceARN' \
  --output text 2>/dev/null)

COUNT=$(echo "${RESOURCES}" | wc -w | tr -d ' ')

echo ""
echo "    Resources found: ${COUNT}"
echo ""
echo "    ARN list:"
echo "${RESOURCES}" | tr '\t' '\n' | sort

echo ""
if [[ "${COUNT}" -lt 10 ]]; then
  echo "WARN: Only ${COUNT} resources found with Project=colab,Env=${ENV} tags."
  echo "      Expected at least 10 after a full terraform apply."
  echo "      Check: (1) terraform applied, (2) default_tags set in provider block."
  exit 1
else
  echo "PASS: Found ${COUNT} resources tagged Project=colab,Env=${ENV}."
fi
