#!/usr/bin/env bash
# =============================================================================
# bake_claim_cert.sh — fetch claim cert from Secrets Manager into robot image
#
# Run during robot Dockerfile build or factory imaging.
# Requires AWS credentials with secretsmanager:GetSecretValue permission.
#
# Usage:
#   export AWS_REGION=ap-northeast-1
#   export ENV=dev
#   export CERTS_DIR=/etc/robotops/certs   # default
#   ./scripts/iot/bake_claim_cert.sh
# =============================================================================
set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-1}"
ENV="${ENV:-dev}"
CERTS_DIR="${CERTS_DIR:-/etc/robotops/certs}"
SECRET_PREFIX="robotops/${ENV}/iot/claim"

echo "Fetching claim certs (env=${ENV}) → ${CERTS_DIR}"
mkdir -p "${CERTS_DIR}"

aws secretsmanager get-secret-value \
  --secret-id "${SECRET_PREFIX}/cert" \
  --region "${REGION}" \
  --query SecretString \
  --output text > "${CERTS_DIR}/claim.crt"

aws secretsmanager get-secret-value \
  --secret-id "${SECRET_PREFIX}/key" \
  --region "${REGION}" \
  --query SecretString \
  --output text > "${CERTS_DIR}/claim.key"

aws secretsmanager get-secret-value \
  --secret-id "${SECRET_PREFIX}/root-ca" \
  --region "${REGION}" \
  --query SecretString \
  --output text > "${CERTS_DIR}/AmazonRootCA1.pem"

chmod 600 "${CERTS_DIR}/claim.key"
echo "Claim certs written to ${CERTS_DIR}"
