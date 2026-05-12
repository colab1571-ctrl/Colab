#!/usr/bin/env bash
# smoke/celery_test.sh — Send a Celery test task via Amazon MQ and verify it processes.
# Usage: ENV=dev bash scripts/smoke/celery_test.sh
# Requires: kubectl, AWS CLI, running hello-svc or celery worker deployment in the namespace.
set -euo pipefail

ENV="${ENV:-dev}"
CLUSTER_NAME="colab-${ENV}"
NAMESPACE="colab-${ENV}"
REGION="${AWS_REGION:-us-east-1}"
TASK_TIMEOUT="${TASK_TIMEOUT:-30}"

echo "==> Celery Smoke: env=${ENV}"

aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${REGION}" --quiet

# Find a running celery worker pod
WORKER_POD=$(kubectl get pods -n "${NAMESPACE}" -l "role=celery-worker" \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [[ -z "${WORKER_POD}" ]]; then
  echo "WARN: No celery-worker pod found in ${NAMESPACE}. Trying any app pod..."
  WORKER_POD=$(kubectl get pods -n "${NAMESPACE}" \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
fi

if [[ -z "${WORKER_POD}" ]]; then
  echo "ERROR: No running pods found in namespace ${NAMESPACE}."
  exit 1
fi

echo "    Using pod: ${WORKER_POD}"

# Submit a Celery debug task and capture the task ID
TASK_ID=$(kubectl exec -n "${NAMESPACE}" "${WORKER_POD}" -- \
  python -c "
from celery import Celery
import os
app = Celery(broker=os.environ['RABBITMQ_URL'])
result = app.send_task('colab.tasks.debug_ping', args=['smoke-test'], countdown=0)
print(result.id)
" 2>/dev/null)

echo "    Task submitted: ${TASK_ID}"
echo "    Waiting up to ${TASK_TIMEOUT}s for task completion..."

# Poll for task result
for i in $(seq 1 "${TASK_TIMEOUT}"); do
  STATUS=$(kubectl exec -n "${NAMESPACE}" "${WORKER_POD}" -- \
    python -c "
from celery.result import AsyncResult
from celery import Celery
import os
app = Celery(broker=os.environ['RABBITMQ_URL'], backend='rpc://')
r = AsyncResult('${TASK_ID}', app=app)
print(r.status)
" 2>/dev/null || echo "PENDING")

  echo "    [${i}/${TASK_TIMEOUT}] Status: ${STATUS}"
  if [[ "${STATUS}" == "SUCCESS" ]]; then
    echo "PASS: Celery task ${TASK_ID} completed successfully."
    exit 0
  fi
  sleep 1
done

echo "FAIL: Celery task ${TASK_ID} did not complete within ${TASK_TIMEOUT}s. Final status: ${STATUS}"
exit 1
