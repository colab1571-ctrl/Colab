#!/usr/bin/env bash
# smoke/eks_nodes.sh — Verify EKS cluster nodes are Ready.
# Usage: ENV=dev bash scripts/smoke/eks_nodes.sh
set -euo pipefail

ENV="${ENV:-dev}"
CLUSTER_NAME="colab-${ENV}"
REGION="${AWS_REGION:-us-east-1}"
MIN_NODES="${MIN_NODES:-2}"

echo "==> EKS Smoke: checking nodes in cluster=${CLUSTER_NAME}"

aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${REGION}" --quiet

READY_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready " || true)

echo "    Ready nodes: ${READY_COUNT} (minimum required: ${MIN_NODES})"

if [[ "${READY_COUNT}" -lt "${MIN_NODES}" ]]; then
  echo "FAIL: Only ${READY_COUNT} nodes Ready; expected at least ${MIN_NODES}"
  kubectl get nodes
  exit 1
fi

echo "    Node details:"
kubectl get nodes -o wide

echo ""
echo "PASS: EKS cluster ${CLUSTER_NAME} has ${READY_COUNT} Ready nodes."
