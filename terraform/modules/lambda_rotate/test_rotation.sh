#!/bin/bash
# Manual test script for RDS password rotation
# Usage: bash terraform/modules/lambda_rotate/test_rotation.sh <secret-id> <rds-instance-id>
# Example: bash terraform/modules/lambda_rotate/test_rotation.sh anpr/database anpr-db

set -e

SECRET_ID="${1:-anpr/database}"
RDS_INSTANCE_ID="${2:-anpr-db}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "=========================================="
echo "RDS Password Rotation Test"
echo "=========================================="
echo "Secret ID: $SECRET_ID"
echo "RDS Instance: $RDS_INSTANCE_ID"
echo "Region: $AWS_REGION"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
command -v aws &>/dev/null || { echo "✗ AWS CLI not installed"; exit 1; }
command -v jq &>/dev/null || { echo "✗ jq not installed"; exit 1; }
echo "✓ Prerequisites met"
echo ""

# Verify secret exists
echo "Verifying secret exists..."
SECRET_ARN=$(aws secretsmanager describe-secret \
  --secret-id "$SECRET_ID" \
  --region "$AWS_REGION" \
  --query "ARN" \
  --output text 2>/dev/null) || {
  echo "✗ Secret not found: $SECRET_ID"
  exit 1
}
echo "✓ Secret found: $SECRET_ARN"
echo ""

# Verify RDS instance exists
echo "Verifying RDS instance exists..."
RDS_STATUS=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query "DBInstances[0].DBInstanceStatus" \
  --output text 2>/dev/null) || {
  echo "✗ RDS instance not found: $RDS_INSTANCE_ID"
  exit 1
}
echo "✓ RDS instance found, status: $RDS_STATUS"
echo ""

# Verify Lambda function exists
LAMBDA_NAME=$(aws secretsmanager describe-secret \
  --secret-id "$SECRET_ID" \
  --region "$AWS_REGION" \
  --query "RotationRules.RotationLambdaARN" \
  --output text 2>/dev/null | grep -oP "function:\K[^:]+")

if [ -z "$LAMBDA_NAME" ]; then
  echo "⚠ No Lambda rotation function configured for this secret"
  echo "Configure Lambda rotation in Secrets Manager first"
  exit 1
fi
echo "✓ Lambda rotation function: $LAMBDA_NAME"
echo ""

# Get current secret version
echo "Getting current secret state..."
CURRENT_VERSION=$(aws secretsmanager describe-secret \
  --secret-id "$SECRET_ID" \
  --region "$AWS_REGION" \
  --query "VersionIdsToStages" \
  --output json)
echo "Current versions:"
echo "$CURRENT_VERSION" | jq '.'
echo ""

# Trigger rotation
echo "Triggering manual rotation..."
ROTATION_OUTPUT=$(aws secretsmanager rotate-secret \
  --secret-id "$SECRET_ID" \
  --region "$AWS_REGION" \
  --output json 2>&1) || {
  ERROR_MSG=$(echo "$ROTATION_OUTPUT" | grep -o "Error.*" || echo "Unknown error")
  echo "✗ Rotation trigger failed: $ERROR_MSG"
  exit 1
}

VERSION_ID=$(echo "$ROTATION_OUTPUT" | jq -r '.VersionId')
ROTATION_NAME=$(echo "$ROTATION_OUTPUT" | jq -r '.Name')

echo "✓ Rotation triggered"
echo "Version ID: $VERSION_ID"
echo ""

# Monitor rotation progress (with timeout)
echo "Monitoring rotation progress..."
TIMEOUT=120  # 2 minute timeout
ELAPSED=0
POLL_INTERVAL=5

while [ $ELAPSED -lt $TIMEOUT ]; do
  ROTATION_STATUS=$(aws secretsmanager describe-secret \
    --secret-id "$SECRET_ID" \
    --region "$AWS_REGION" \
    --query "VersionIdsToStages" \
    --output json)

  PENDING_VERSIONS=$(echo "$ROTATION_STATUS" | jq 'keys[] | select(contains("AWSPENDING"))')

  if [ -z "$PENDING_VERSIONS" ]; then
    echo "✓ Rotation completed!"
    echo ""
    echo "Final version state:"
    echo "$ROTATION_STATUS" | jq '.'
    break
  fi

  ELAPSED=$((ELAPSED + POLL_INTERVAL))
  PERCENT=$((ELAPSED * 100 / TIMEOUT))
  echo -ne "\rWaiting... ${PERCENT}% (${ELAPSED}s)"
  sleep $POLL_INTERVAL
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo ""
  echo "⚠ Rotation timeout after ${TIMEOUT}s"
  echo "Check CloudWatch logs: /aws/lambda/$LAMBDA_NAME"
  exit 1
fi

echo ""
echo "=========================================="
echo "✓ Rotation test completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Check CloudWatch logs: /aws/lambda/$LAMBDA_NAME"
echo "2. Verify RDS password was updated"
echo "3. Test application connectivity"
echo ""
