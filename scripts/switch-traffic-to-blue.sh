#!/bin/bash
set -e

# Switch traffic back to blue (previous/stable version) for rollback

echo "Rolling back: switching traffic to blue environment..."

# Update load balancer/reverse proxy configuration back to port 8000
if [ -f "/etc/nginx/conf.d/anpr-upstream.conf" ]; then
  sudo sed -i 's/server localhost:8001/server localhost:8000/' /etc/nginx/conf.d/anpr-upstream.conf
  sudo nginx -t && sudo systemctl reload nginx
  echo "Nginx upstream reverted to blue"
fi

if [ -f "/etc/haproxy/haproxy.cfg" ]; then
  sudo sed -i 's/server api1 localhost:8001/server api1 localhost:8000/' /etc/haproxy/haproxy.cfg
  sudo systemctl reload haproxy
  echo "HAProxy backend reverted to blue"
fi

sleep 2
if curl -f http://localhost/healthz > /dev/null 2>&1; then
  echo "Traffic successfully switched back to blue"
else
  echo "Failed to route traffic to blue"
  exit 1
fi

echo "Rollback complete"
