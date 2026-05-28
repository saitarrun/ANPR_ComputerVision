#!/bin/bash
set -e

# Switch traffic from blue (production) to green (new) via load balancer/reverse proxy
# This script is called during blue-green deployments

PROD_PATH="/opt/anpr/prod"
LB_HEALTH_CHECK_URL="http://localhost:8001/healthz"
MAX_RETRIES=5

echo "Switching traffic to green environment..."

# Verify green is healthy
for i in $(seq 1 $MAX_RETRIES); do
  if curl -f "$LB_HEALTH_CHECK_URL" > /dev/null 2>&1; then
    echo "Green environment is healthy"
    break
  fi
  if [ $i -eq $MAX_RETRIES ]; then
    echo "Green environment is not healthy"
    exit 1
  fi
  sleep 2
done

# Update load balancer/reverse proxy configuration
# Example: update nginx upstream to point to port 8001 (green) instead of 8000 (blue)
if [ -f "/etc/nginx/conf.d/anpr-upstream.conf" ]; then
  sudo sed -i 's/server localhost:8000/server localhost:8001/' /etc/nginx/conf.d/anpr-upstream.conf
  sudo nginx -t && sudo systemctl reload nginx
  echo "Nginx upstream updated to green"
fi

# Alternative: if using HAProxy
if [ -f "/etc/haproxy/haproxy.cfg" ]; then
  sudo sed -i 's/server api1 localhost:8000/server api1 localhost:8001/' /etc/haproxy/haproxy.cfg
  sudo systemctl reload haproxy
  echo "HAProxy backend updated to green"
fi

# Verify traffic is routed correctly
sleep 5
if curl -f http://localhost/healthz > /dev/null 2>&1; then
  echo "Traffic successfully switched to green"
else
  echo "Failed to route traffic to green"
  exit 1
fi

echo "Traffic switch complete"
