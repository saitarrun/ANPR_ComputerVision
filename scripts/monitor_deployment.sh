#!/bin/bash
# Monitor ECS deployment and auto-rollback on SLO breach
# Tracks error rate, latency, and resource utilization during deployment window

set -euo pipefail

CLUSTER=""
SERVICE=""
DURATION="30m"
ERROR_THRESHOLD=5  # Error rate %
LATENCY_THRESHOLD=1000  # P99 latency in ms
POLL_INTERVAL=30  # seconds
REGION="us-east-1"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --cluster) CLUSTER="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --error-threshold) ERROR_THRESHOLD="$2"; shift 2 ;;
    --latency-threshold) LATENCY_THRESHOLD="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [[ -z "$CLUSTER" ]] || [[ -z "$SERVICE" ]]; then
  echo "Usage: $0 --cluster <name> --service <name> [--duration <30m>] [--error-threshold <5>] [--latency-threshold <1000>]"
  exit 1
fi

# Convert duration to seconds
convert_duration() {
  local duration=$1
  if [[ $duration =~ ^([0-9]+)m$ ]]; then
    echo $((${BASH_REMATCH[1]} * 60))
  elif [[ $duration =~ ^([0-9]+)s$ ]]; then
    echo "${BASH_REMATCH[1]}"
  else
    echo 1800  # default 30 minutes
  fi
}

DURATION_SECONDS=$(convert_duration "$DURATION")
END_TIME=$(($(date +%s) + DURATION_SECONDS))

echo "Starting deployment monitoring for $CLUSTER/$SERVICE"
echo "Duration: $DURATION ($DURATION_SECONDS seconds)"
echo "Error threshold: ${ERROR_THRESHOLD}%"
echo "Latency threshold: ${LATENCY_THRESHOLD}ms"
echo ""

# Function to get metrics from CloudWatch
get_metrics() {
  local metric_name=$1
  local stat=$2

  aws cloudwatch get-metric-statistics \
    --namespace AWS/ECS \
    --metric-name "$metric_name" \
    --dimensions Name=ServiceName,Value="$SERVICE" Name=ClusterName,Value="$CLUSTER" \
    --start-time "$(date -u -d '5 minutes ago' +'%Y-%m-%dT%H:%M:%S')" \
    --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
    --period 60 \
    --statistics "$stat" \
    --region "$REGION" \
    --query 'Datapoints[0]' \
    --output json || echo "{}"
}

# Monitor loop
while [[ $(date +%s) -lt $END_TIME ]]; do
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] Checking metrics..."

  # Get CPU and memory utilization
  cpu_util=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/ECS \
    --metric-name CPUUtilization \
    --dimensions Name=ServiceName,Value="$SERVICE" Name=ClusterName,Value="$CLUSTER" \
    --start-time "$(date -u -d '1 minute ago' +'%Y-%m-%dT%H:%M:%S')" \
    --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
    --period 60 \
    --statistics Average \
    --region "$REGION" \
    --query 'Datapoints[0].Average' \
    --output text)

  memory_util=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/ECS \
    --metric-name MemoryUtilization \
    --dimensions Name=ServiceName,Value="$SERVICE" Name=ClusterName,Value="$CLUSTER" \
    --start-time "$(date -u -d '1 minute ago' +'%Y-%m-%dT%H:%M:%S')" \
    --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
    --period 60 \
    --statistics Average \
    --region "$REGION" \
    --query 'Datapoints[0].Average' \
    --output text)

  # Get ALB metrics (error rate, latency)
  # Note: These are custom metrics published by the application
  error_rate=$(aws cloudwatch get-metric-statistics \
    --namespace ANPR/API \
    --metric-name ErrorRate \
    --start-time "$(date -u -d '1 minute ago' +'%Y-%m-%dT%H:%M:%S')" \
    --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
    --period 60 \
    --statistics Average \
    --region "$REGION" \
    --query 'Datapoints[0].Average' \
    --output text)

  p99_latency=$(aws cloudwatch get-metric-statistics \
    --namespace ANPR/API \
    --metric-name RequestLatencyP99 \
    --start-time "$(date -u -d '1 minute ago' +'%Y-%m-%dT%H:%M:%S')" \
    --end-time "$(date -u +'%Y-%m-%dT%H:%M:%S')" \
    --period 60 \
    --statistics Average \
    --region "$REGION" \
    --query 'Datapoints[0].Average' \
    --output text)

  # Display metrics
  echo "  CPU: ${cpu_util}% | Memory: ${memory_util}% | Error Rate: ${error_rate}% | P99 Latency: ${p99_latency}ms"

  # Check thresholds
  if [[ $(echo "$error_rate > $ERROR_THRESHOLD" | bc -l) -eq 1 ]]; then
    echo "❌ ERROR RATE THRESHOLD BREACHED: ${error_rate}% > ${ERROR_THRESHOLD}%"
    echo "Initiating automatic rollback..."
    exit 1
  fi

  if [[ $(echo "$p99_latency > $LATENCY_THRESHOLD" | bc -l) -eq 1 ]]; then
    echo "⚠️  LATENCY THRESHOLD BREACHED: ${p99_latency}ms > ${LATENCY_THRESHOLD}ms"
    # Note: Don't auto-rollback on latency alone; could be legitimate spike
  fi

  sleep "$POLL_INTERVAL"
done

echo "✅ Deployment monitoring completed successfully"
exit 0
