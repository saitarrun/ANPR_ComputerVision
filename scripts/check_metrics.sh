#!/bin/bash
# Display current deployment metrics
# Used during post-deployment monitoring

set -euo pipefail

CLUSTER="${1:-anpr-prod-ecs-cluster}"
SERVICE="${2:-anpr-prod-ecs-service-green}"
REGION="us-east-1"

echo "=== Deployment Metrics ==="
echo "Time: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo ""

# ECS Service Status
echo "--- ECS Service Status ---"
aws ecs describe-services \
  --cluster "$CLUSTER" \
  --services "$SERVICE" \
  --region "$REGION" \
  --query 'services[0].{Desired: desiredCount, Running: runningCount, Pending: pendingCount, Status: status}' \
  --output table

echo ""

# Task Health
echo "--- Task Health ---"
aws ecs describe-tasks \
  --cluster "$CLUSTER" \
  --tasks "$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --region "$REGION" --query 'taskArns[0]' --output text)" \
  --region "$REGION" \
  --query 'tasks[0].{LastStatus: lastStatus, DesiredStatus: desiredStatus, CPU: cpu, Memory: memory}' \
  --output table 2>/dev/null || echo "No running tasks"

echo ""

# CloudWatch Metrics (last 5 minutes)
echo "--- Error Rate (last 5 minutes) ---"
aws cloudwatch get-metric-statistics \
  --namespace ANPR/API \
  --metric-name ErrorRate \
  --start-time "$(date -u -d '5 minutes ago' +'%Y-%m-%dT%H:%M:%S')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
  --period 60 \
  --statistics Average \
  --region "$REGION" \
  --output table | grep -A 10 "Average" || echo "No data"

echo ""

# Latency (P99)
echo "--- Latency P99 (last 5 minutes) ---"
aws cloudwatch get-metric-statistics \
  --namespace ANPR/API \
  --metric-name RequestLatencyP99 \
  --start-time "$(date -u -d '5 minutes ago' +'%Y-%m-%dT%H:%M:%S')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
  --period 60 \
  --statistics Average \
  --region "$REGION" \
  --output table | grep -A 10 "Average" || echo "No data"

echo ""

# CPU Utilization
echo "--- CPU Utilization ---"
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value="$SERVICE" Name=ClusterName,Value="$CLUSTER" \
  --start-time "$(date -u -d '5 minutes ago' +'%Y-%m-%dT%H:%M:%S')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
  --period 60 \
  --statistics Average \
  --region "$REGION" \
  --output table | grep -A 10 "Average" || echo "No data"

echo ""

# Memory Utilization
echo "--- Memory Utilization ---"
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name MemoryUtilization \
  --dimensions Name=ServiceName,Value="$SERVICE" Name=ClusterName,Value="$CLUSTER" \
  --start-time "$(date -u -d '5 minutes ago' +'%Y-%m-%dT%H:%M:%S')" \
  --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
  --period 60 \
  --statistics Average \
  --region "$REGION" \
  --output table | grep -A 10 "Average" || echo "No data"

echo ""
echo "=== End Metrics ==="
