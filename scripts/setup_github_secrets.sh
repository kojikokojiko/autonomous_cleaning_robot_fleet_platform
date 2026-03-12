#!/usr/bin/env bash
# =============================================================================
# setup_github_secrets.sh — configure GitHub Actions secrets & variables
#
# Run AFTER `terraform apply` completes.
# Reads Terraform outputs and sets secrets/variables on the GitHub repo.
#
# Prerequisites:
#   - `gh` CLI installed and authenticated (gh auth login)
#   - `terraform` installed
#   - AWS credentials available (to run terraform output)
#
# Usage:
#   export GITHUB_REPO=myorg/autonomous_cleaning_robot_fleet_platform
#   ./scripts/setup_github_secrets.sh
# =============================================================================
set -euo pipefail

GITHUB_REPO="${GITHUB_REPO:-}"
TF_DIR="infrastructure/terraform/environments/dev"

if [[ -z "${GITHUB_REPO}" ]]; then
  echo "ERROR: Set GITHUB_REPO=owner/repo before running this script."
  exit 1
fi

command -v gh      >/dev/null || { echo "ERROR: gh CLI not found. Install: https://cli.github.com"; exit 1; }
command -v terraform >/dev/null || { echo "ERROR: terraform not found."; exit 1; }

echo "=== Reading Terraform outputs from ${TF_DIR} ==="
cd "${TF_DIR}"

_tf_output() { terraform output -raw "$1" 2>/dev/null; }

ROLE_ARN=$(          _tf_output github_actions_role_arn)
ACCOUNT_ID=$(        _tf_output account_id)
DASHBOARD_BUCKET=$(  _tf_output dashboard_bucket)
CF_DIST_ID=$(        _tf_output cloudfront_distribution_id)
API_ENDPOINT=$(      _tf_output api_endpoint)
WS_ENDPOINT=$(       _tf_output ws_endpoint)

cd - >/dev/null

echo ""
echo "Values to configure:"
echo "  AWS_ROLE_ARN:              ${ROLE_ARN}"
echo "  AWS_ACCOUNT_ID:            ${ACCOUNT_ID}"
echo "  DASHBOARD_BUCKET:          ${DASHBOARD_BUCKET}"
echo "  CLOUDFRONT_DISTRIBUTION_ID: ${CF_DIST_ID}"
echo "  VITE_API_URL (variable):   ${API_ENDPOINT}"
echo "  VITE_WS_URL  (variable):   ${WS_ENDPOINT}"
echo ""

# ── Secrets (encrypted) ───────────────────────────────────────────────────
echo "=== Setting GitHub Actions Secrets ==="

gh secret set AWS_ROLE_ARN               --body "${ROLE_ARN}"        --repo "${GITHUB_REPO}"
echo "  ✓ AWS_ROLE_ARN"

gh secret set AWS_ACCOUNT_ID             --body "${ACCOUNT_ID}"      --repo "${GITHUB_REPO}"
echo "  ✓ AWS_ACCOUNT_ID"

gh secret set DASHBOARD_BUCKET           --body "${DASHBOARD_BUCKET}" --repo "${GITHUB_REPO}"
echo "  ✓ DASHBOARD_BUCKET"

gh secret set CLOUDFRONT_DISTRIBUTION_ID --body "${CF_DIST_ID}"      --repo "${GITHUB_REPO}"
echo "  ✓ CLOUDFRONT_DISTRIBUTION_ID"

# ── Variables (plaintext, visible in logs) ────────────────────────────────
echo ""
echo "=== Setting GitHub Actions Variables ==="

gh variable set VITE_API_URL --body "${API_ENDPOINT}" --repo "${GITHUB_REPO}"
echo "  ✓ VITE_API_URL"

gh variable set VITE_WS_URL  --body "${WS_ENDPOINT}"  --repo "${GITHUB_REPO}"
echo "  ✓ VITE_WS_URL"

echo ""
echo "=== Done ==="
echo ""
echo "Verify at: https://github.com/${GITHUB_REPO}/settings/secrets/actions"
