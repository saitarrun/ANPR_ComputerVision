#!/bin/bash
# ANPR Cost Monitoring & Reporting Script
#
# Usage:
#   ./scripts/cost_monitoring.sh monthly          # Monthly cost breakdown
#   ./scripts/cost_monitoring.sh daily            # Today's cost
#   ./scripts/cost_monitoring.sh forecast         # Forecast end-of-month
#   ./scripts/cost_monitoring.sh validate-optimization # Check optimization effectiveness
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - jq for JSON parsing
#   - curl for Slack notifications (optional)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
COST_BUDGET_MONTHLY_PROD=150          # Expected monthly cost (prod optimized)
COST_BUDGET_MONTHLY_STAGE=100         # Expected monthly cost (stage)
COST_BUDGET_MONTHLY_DEV=50            # Expected monthly cost (dev)
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"    # Optional: Slack webhook for alerts

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
  echo "[INFO] $(date '+%Y-%m-%d %H:%M:%S') - $*"
}

log_error() {
  echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') - $*" >&2
}

log_warn() {
  echo "[WARN] $(date '+%Y-%m-%d %H:%M:%S') - $*"
}

send_slack_alert() {
  local message="$1"
  if [[ -z "$SLACK_WEBHOOK" ]]; then
    return
  fi

  curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\": \"$message\"}" \
    "$SLACK_WEBHOOK" >/dev/null 2>&1 || true
}

# ============================================================================
# Monthly Cost Breakdown
# ============================================================================

monthly_cost_report() {
  log_info "Generating monthly cost report..."

  local start_date=$(date -d "1 month ago" +%Y-%m-01)
  local end_date=$(date +%Y-%m-01)

  log_info "Period: $start_date to $end_date"

  # Total cost by service
  log_info "Cost by Service:"
  aws ce get-cost-and-usage \
    --time-period Start="$start_date",End="$end_date" \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --group-by Type=DIMENSION,Key=SERVICE \
    --region "$AWS_REGION" \
    | jq -r '.ResultsByTime[0].Groups | sort_by(.Metrics.UnblendedCost.Amount | tonumber) | reverse | .[] | "\(.Keys[0]): \(.Metrics.UnblendedCost.Amount) \(.Metrics.UnblendedCost.Unit)"' \
    | column -t

  echo ""

  # Total cost by environment (via tags)
  log_info "Cost by Environment:"
  aws ce get-cost-and-usage \
    --time-period Start="$start_date",End="$end_date" \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --filter '{
      "Dimensions": {
        "Key": "TAG",
        "Values": ["prod", "stage", "dev"]
      }
    }' \
    --region "$AWS_REGION" \
    | jq -r '.ResultsByTime[0].Groups | sort_by(.Metrics.UnblendedCost.Amount | tonumber) | reverse | .[] | "\(.Keys[0]): $\(.Metrics.UnblendedCost.Amount)"' \
    || log_warn "Tag-based filtering not available (tags may not be applied yet)"

  echo ""

  # Top 10 services
  log_info "Top 10 Cost Drivers:"
  aws ce get-cost-and-usage \
    --time-period Start="$start_date",End="$end_date" \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --group-by Type=DIMENSION,Key=SERVICE \
    --region "$AWS_REGION" \
    | jq -r '.ResultsByTime[0].Groups | sort_by(.Metrics.UnblendedCost.Amount | tonumber) | reverse | .[0:10] | .[] | "\(.Keys[0]): \(.Metrics.UnblendedCost.Amount)"' \
    | nl
}

# ============================================================================
# Daily Cost Report
# ============================================================================

daily_cost_report() {
  log_info "Generating today's cost report..."

  local today=$(date +%Y-%m-%d)
  local tomorrow=$(date -d "+1 day" +%Y-%m-%d)

  log_info "Date: $today"

  aws ce get-cost-and-usage \
    --time-period Start="$today",End="$tomorrow" \
    --granularity DAILY \
    --metrics "UnblendedCost" \
    --group-by Type=DIMENSION,Key=SERVICE \
    --region "$AWS_REGION" \
    | jq -r '.ResultsByTime[0].Groups | sort_by(.Metrics.UnblendedCost.Amount | tonumber) | reverse | .[] | "\(.Keys[0]): $\(.Metrics.UnblendedCost.Amount)"' \
    || log_warn "No cost data for today yet (data is usually available after 24 hours)"
}

# ============================================================================
# Forecast End-of-Month Cost
# ============================================================================

forecast_eom_cost() {
  log_info "Forecasting end-of-month cost..."

  local month_start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d)
  local today=$(date +%Y-%m-%d)
  local month_end=$(date -d "$(date +%Y-%m-01) +1 month -1 day" +%Y-%m-%d)
  local days_passed=$((($(date -d "$today" +%s) - $(date -d "$month_start" +%s)) / 86400 + 1))
  local days_total=$((($(date -d "$month_end" +%s) - $(date -d "$month_start" +%s)) / 86400 + 1))

  log_info "Days passed: $days_passed / $days_total"

  # Get cost so far this month
  local current_cost=$(aws ce get-cost-and-usage \
    --time-period Start="$month_start",End="$today" \
    --granularity MONTHLY \
    --metrics "UnblendedCost" \
    --region "$AWS_REGION" \
    | jq '.ResultsByTime[0].Total.UnblendedCost.Amount | tonumber')

  # Forecast
  local forecasted_cost=$(echo "scale=2; $current_cost * $days_total / $days_passed" | bc)

  log_info "Current cost (as of $today): \$$current_cost"
  log_info "Forecasted month-end cost: \$$forecasted_cost"

  # Compare to budget
  local budget=$COST_BUDGET_MONTHLY_PROD
  if [[ $(echo "$forecasted_cost > $budget * 1.1" | bc -l) -eq 1 ]]; then
    log_warn "ALERT: Forecasted cost (\$$forecasted_cost) exceeds budget (\$$budget) by >10%"
    send_slack_alert ":warning: ANPR Cost Alert: Forecasted month-end cost \$$forecasted_cost exceeds budget \$$budget"
  fi
}

# ============================================================================
# Validate Optimization Effectiveness
# ============================================================================

validate_optimization() {
  log_info "Validating cost optimization effectiveness..."

  echo ""
  log_info "1. ECS Task Utilization (Target: CPU 40-60% avg, <80% peak)"
  aws cloudwatch get-metric-statistics \
    --namespace AWS/ECS \
    --metric-name CPUUtilization \
    --dimensions Name=ServiceName,Value=anpr-api \
    --start-time "$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S)Z" \
    --end-time "$(date -u +%Y-%m-%dT%H:%M:%S)Z" \
    --period 3600 \
    --statistics Average,Maximum \
    --region "$AWS_REGION" \
    | jq '.Datapoints | sort_by(.Timestamp) | reverse | .[0:7] | .[] | "\(.Timestamp): Avg=\(.Average)%, Max=\(.Maximum)%"' \
    | column -t \
    || log_warn "ECS metrics not available (service may not be deployed)"

  echo ""
  log_info "2. Autoscaling Activity (Should scale up at 70% CPU, down at 40%)"
  aws autoscaling describe-scaling-activities \
    --auto-scaling-group-name "anpr-ecs-asg" \
    --max-records 10 \
    --region "$AWS_REGION" \
    2>/dev/null \
    | jq '.Activities[] | "\(.StartTime): \(.Description) (Cause: \(.Cause))"' \
    | head -5 \
    || log_warn "Autoscaling activities not found (ASG may not exist yet)"

  echo ""
  log_info "3. RDS CPU & Connections (Target: <70% CPU avg)"
  aws cloudwatch get-metric-statistics \
    --namespace AWS/RDS \
    --metric-name CPUUtilization \
    --dimensions Name=DBInstanceIdentifier,Value=anpr-prod \
    --start-time "$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S)Z" \
    --end-time "$(date -u +%Y-%m-%dT%H:%M:%S)Z" \
    --period 3600 \
    --statistics Average,Maximum \
    --region "$AWS_REGION" \
    | jq '.Datapoints | sort_by(.Timestamp) | reverse | .[0:7] | .[] | "\(.Timestamp): Avg=\(.Average)%, Max=\(.Maximum)%"' \
    | column -t \
    || log_warn "RDS metrics not available"

  echo ""
  log_info "4. S3 Storage Classes (Should see Standard → IA → Glacier transition)"
  for bucket in anpr-frames anpr-crops anpr-audit; do
    log_info "  Bucket: $bucket"
    aws s3api list-objects-v2 \
      --bucket "$bucket" \
      --region "$AWS_REGION" \
      --query 'Contents[].[StorageClass]' \
      2>/dev/null \
      | jq -s 'group_by(.[0]) | map({class: .[0][0], count: length}) | sort_by(.count) | reverse | .[] | "    \(.class): \(.count) objects"' \
      || log_warn "    Bucket not found or not accessible"
  done

  echo ""
  log_info "5. ElastiCache Node Status (Should show healthy metrics)"
  aws elasticache describe-cache-clusters \
    --cache-cluster-id "anpr-redis" \
    --region "$AWS_REGION" \
    --show-cache-node-info \
    2>/dev/null \
    | jq '.CacheClusters[0] | "Engine: \(.Engine), NodeType: \(.CacheNodeType), Nodes: \(.CacheNodes | length), Status: \(.CacheClusterStatus)"' \
    || log_warn "ElastiCache cluster not found"

  echo ""
  log_info "Cost Optimization Validation Complete"
}

# ============================================================================
# Main
# ============================================================================

main() {
  local command="${1:-monthly}"

  case "$command" in
    monthly)
      monthly_cost_report
      ;;
    daily)
      daily_cost_report
      ;;
    forecast)
      forecast_eom_cost
      ;;
    validate-optimization|validate)
      validate_optimization
      ;;
    *)
      log_error "Unknown command: $command"
      echo ""
      echo "Usage: $0 {monthly|daily|forecast|validate-optimization}"
      echo ""
      echo "Commands:"
      echo "  monthly                 - Monthly cost breakdown by service"
      echo "  daily                   - Today's cost by service"
      echo "  forecast                - Forecast end-of-month cost"
      echo "  validate-optimization   - Validate optimization effectiveness (CPU, scaling, storage tiers)"
      echo ""
      exit 1
      ;;
  esac
}

main "$@"
