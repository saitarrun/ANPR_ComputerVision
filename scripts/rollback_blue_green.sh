#!/bin/bash
# Rollback blue-green deployment
# Instantly reverts traffic to previous variant via ALB target group

set -euo pipefail

REGION="us-east-1"
ENVIRONMENT="${1:-prod}"
ALB_ARN="arn:aws:elasticloadbalancing:${REGION}:ACCOUNT:loadbalancer/app/anpr-${ENVIRONMENT}-alb/..."
LISTENER_ARN="arn:aws:elasticloadbalancing:${REGION}:ACCOUNT:listener/app/anpr-${ENVIRONMENT}-alb/..."

# Get current active target group
echo "Determining current active deployment..."
current_active=$(aws elbv2 describe-listeners \
  --listener-arn "$LISTENER_ARN" \
  --region "$REGION" \
  --query 'Listeners[0].DefaultActions[0].TargetGroupArn' \
  --output text)

if [[ "$current_active" == *"green"* ]]; then
  new_target="blue"
  old_target="green"
else
  new_target="green"
  old_target="blue"
fi

echo "Current active: $old_target"
echo "Rolling back to: $new_target"

# Get target group ARN for rollback variant
rollback_tg=$(aws elbv2 describe-target-groups \
  --names "anpr-${ENVIRONMENT}-${new_target}" \
  --region "$REGION" \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

if [[ -z "$rollback_tg" ]]; then
  echo "❌ ERROR: Could not find target group for $new_target variant"
  exit 1
fi

echo "Target Group ARN: $rollback_tg"

# Update listener to point to rollback variant
echo "Switching ALB traffic back to $new_target..."
aws elbv2 modify-listener \
  --listener-arn "$LISTENER_ARN" \
  --default-actions Type=forward,TargetGroupArn="$rollback_tg" \
  --region "$REGION"

echo "✅ Traffic switched to $new_target variant"
echo ""

# Scale down the failed variant
echo "Scaling down failed $old_target variant..."
aws ecs update-service \
  --cluster "anpr-${ENVIRONMENT}-ecs-cluster" \
  --service "anpr-${ENVIRONMENT}-ecs-service-${old_target}" \
  --desired-count 0 \
  --region "$REGION"

echo "✅ Rollback complete"
echo ""
echo "## Rollback Summary"
echo "- From: $old_target"
echo "- To: $new_target"
echo "- Time: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "- Environment: $ENVIRONMENT"
echo ""
echo "Next steps:"
echo "1. Check CloudWatch logs for error details: /ecs/anpr/$ENVIRONMENT"
echo "2. Review the failed deployment in the GitHub Actions workflow"
echo "3. Fix the issue and re-deploy"
