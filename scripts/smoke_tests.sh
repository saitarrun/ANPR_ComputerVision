#!/bin/bash
# Smoke tests for ANPR backend deployment
# Validates that core endpoints are responding and within acceptable latency

set -euo pipefail

API_URL="${1:-http://localhost:8000}"
TIMEOUT=10
LATENCY_THRESHOLD_MS=1000
ERROR_COUNT=0

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
  echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

test_endpoint() {
  local method=$1
  local path=$2
  local expected_status=$3
  local description=$4

  log_info "Testing: $description"

  # Measure latency
  start_time=$(date +%s%N)
  response=$(curl -s -w "\n%{http_code}" -X "$method" \
    --connect-timeout "$TIMEOUT" \
    --max-time "$TIMEOUT" \
    "$API_URL$path" 2>&1 || true)
  end_time=$(date +%s%N)

  # Extract status code (last line)
  status_code=$(echo "$response" | tail -n1)
  latency_ms=$(( (end_time - start_time) / 1000000 ))

  # Check status code
  if [[ "$status_code" == "$expected_status" ]]; then
    log_info "✓ Status code: $status_code (expected $expected_status)"
  else
    log_error "✗ Status code: $status_code (expected $expected_status)"
    ((ERROR_COUNT++))
    return 1
  fi

  # Check latency
  if [[ $latency_ms -lt $LATENCY_THRESHOLD_MS ]]; then
    log_info "✓ Latency: ${latency_ms}ms (threshold: ${LATENCY_THRESHOLD_MS}ms)"
  else
    log_warn "✗ Latency: ${latency_ms}ms (threshold: ${LATENCY_THRESHOLD_MS}ms)"
    ((ERROR_COUNT++))
  fi
}

# Test health endpoint
test_endpoint "GET" "/healthz" "200" "Health check endpoint"

# Test core API endpoints
test_endpoint "GET" "/api/v1/regions" "200" "List regions endpoint"
test_endpoint "GET" "/api/v1/cameras" "200" "List cameras endpoint"

# Test authentication (should fail without token, but endpoint should exist)
test_endpoint "GET" "/api/v1/detections" "401" "Detections endpoint (auth required)"

# Test 404 on invalid endpoint
test_endpoint "GET" "/api/v1/nonexistent" "404" "Invalid endpoint returns 404"

# Summary
echo ""
if [[ $ERROR_COUNT -eq 0 ]]; then
  log_info "All smoke tests passed!"
  exit 0
else
  log_error "Smoke tests failed with $ERROR_COUNT errors"
  exit 1
fi
