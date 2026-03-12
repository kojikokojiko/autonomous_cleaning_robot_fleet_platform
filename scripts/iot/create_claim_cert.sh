#!/usr/bin/env bash
# =============================================================================
# create_claim_cert.sh — one-time setup: create IoT claim certificate
#
# Creates the bootstrap (claim) certificate used for Fleet Provisioning.
# Run ONCE per environment by an operator with sufficient AWS permissions.
# The cert/key are stored in Secrets Manager for secure retrieval at robot
# image build time (see bake_claim_cert.sh).
#
# Usage:
#   export AWS_REGION=ap-northeast-1
#   export ENV=dev
#   ./scripts/iot/create_claim_cert.sh
# =============================================================================
set -euo pipefail

REGION="${AWS_REGION:-ap-northeast-1}"
ENV="${ENV:-dev}"
POLICY_NAME="robotops-${ENV}-claim-policy"
SECRET_PREFIX="robotops/${ENV}/iot/claim"

echo "=== Creating IoT claim certificate ==="
echo "  env:    ${ENV}"
echo "  region: ${REGION}"
echo "  policy: ${POLICY_NAME}"
echo ""

# 1. Create certificate + key pair
echo "[1/4] Creating certificate..."
CERT_JSON=$(aws iot create-keys-and-certificate \
  --set-as-active \
  --region "${REGION}" \
  --output json)

CERT_ID=$(echo "${CERT_JSON}"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['certificateId'])")
CERT_ARN=$(echo "${CERT_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['certificateArn'])")
CERT_PEM=$(echo "${CERT_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['certificatePem'])")
PRIVATE_KEY=$(echo "${CERT_JSON}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['keyPair']['PrivateKey'])")

echo "  certificate ID: ${CERT_ID}"

# 2. Attach the claim policy (created by Terraform)
echo "[2/4] Attaching claim policy..."
aws iot attach-policy \
  --policy-name "${POLICY_NAME}" \
  --target "${CERT_ARN}" \
  --region "${REGION}"

# 3. Download Amazon Root CA
echo "[3/4] Downloading Amazon Root CA1..."
ROOT_CA=$(curl -sf "https://www.amazontrust.com/repository/AmazonRootCA1.pem")

# 4. Store all three in Secrets Manager
echo "[4/4] Storing in Secrets Manager..."

_upsert_secret() {
  local name="$1" value="$2" desc="$3"
  aws secretsmanager create-secret \
    --name "${name}" \
    --description "${desc}" \
    --secret-string "${value}" \
    --region "${REGION}" 2>/dev/null \
  || aws secretsmanager update-secret \
    --secret-id "${name}" \
    --secret-string "${value}" \
    --region "${REGION}"
}

_upsert_secret "${SECRET_PREFIX}/cert"    "${CERT_PEM}"    "IoT claim certificate PEM (env=${ENV})"
_upsert_secret "${SECRET_PREFIX}/key"     "${PRIVATE_KEY}" "IoT claim private key (env=${ENV})"
_upsert_secret "${SECRET_PREFIX}/root-ca" "${ROOT_CA}"     "Amazon Root CA1 for IoT TLS (env=${ENV})"

echo ""
echo "=== Done ==="
echo ""
echo "Secrets Manager paths:"
echo "  ${SECRET_PREFIX}/cert"
echo "  ${SECRET_PREFIX}/key"
echo "  ${SECRET_PREFIX}/root-ca"
echo ""
echo "Next steps:"
echo "  1. Run scripts/iot/bake_claim_cert.sh during robot image build"
echo "  2. On each new robot's first boot, run:"
echo "       python robot-agent/scripts/provision_robot.py --serial-number <SERIAL>"
