#!/usr/bin/env bash
# smoke/db_extensions.sh — Verify postgis and vector extensions are installed in RDS.
# Usage: ENV=dev bash scripts/smoke/db_extensions.sh
# Requires: kubectl access to the EKS cluster and the rds-url secret in the namespace.
set -euo pipefail

ENV="${ENV:-dev}"
CLUSTER_NAME="colab-${ENV}"
NAMESPACE="colab-${ENV}"
REGION="${AWS_REGION:-us-east-1}"

echo "==> DB Extensions Smoke: env=${ENV}"

aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${REGION}" --quiet

# Get DATABASE_URL from the shared rds-url secret
DATABASE_URL=$(kubectl get secret rds-url -n "${NAMESPACE}" -o jsonpath='{.data.DATABASE_URL}' 2>/dev/null | base64 -d || true)

if [[ -z "${DATABASE_URL}" ]]; then
  echo "WARN: rds-url secret not found in namespace ${NAMESPACE}; using DATABASE_URL env var"
  DATABASE_URL="${DATABASE_URL:-}"
fi

if [[ -z "${DATABASE_URL}" ]]; then
  echo "ERROR: No DATABASE_URL available. Set DATABASE_URL env var or ensure rds-url secret exists."
  exit 1
fi

echo "    Running psql extension check via one-shot pod..."

kubectl run db-smoke-check \
  --rm -it \
  --restart=Never \
  --namespace="${NAMESPACE}" \
  --image=postgres:16 \
  --env="PGPASSWORD=placeholder" \
  --command -- \
  psql "${DATABASE_URL}" -c '\dx' 2>/dev/null | tee /tmp/dx_output.txt

echo ""
echo "    Checking for required extensions..."

if grep -q "postgis" /tmp/dx_output.txt && grep -q "vector" /tmp/dx_output.txt; then
  echo "PASS: Both 'postgis' and 'vector' extensions are installed."
else
  echo "FAIL: One or more extensions missing."
  cat /tmp/dx_output.txt
  exit 1
fi
