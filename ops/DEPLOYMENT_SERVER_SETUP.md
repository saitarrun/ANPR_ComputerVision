# Deployment Server Setup

This guide walks through setting up staging and production servers for automated deployments via GitHub Actions.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ GitHub Actions Workflow                                  │
│  - Validates code                                        │
│  - Builds Docker image                                   │
│  - Triggers SSH deploy script                            │
└──────────────┬───────────────────────────────────────────┘
               │ SSH (key-based auth)
               │
┌──────────────▼───────────────────────────────────────────┐
│ Deployment Server (Staging or Production)                │
│                                                           │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Docker Daemon                                       │  │
│ │  - API container (port 8000)                        │  │
│ │  - Worker container (Celery)                        │  │
│ │  - PostgreSQL (port 5432)                           │  │
│ │  - Redis (port 6379)                                │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                           │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Load Balancer / Reverse Proxy (Nginx/HAProxy)       │  │
│ │  - Routes /api/* → Docker containers                │  │
│ │  - HTTPS termination                                │  │
│ │  - Blue-green traffic switching                     │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                           │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Monitoring (optional)                               │  │
│ │  - Prometheus (metrics scraping)                    │  │
│ │  - Node Exporter (server metrics)                   │  │
│ │  - cAdvisor (container metrics)                     │  │
│ └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

## Prerequisites

- **OS:** Ubuntu 20.04 LTS or later (or compatible Linux)
- **CPU:** 2+ cores
- **RAM:** 4GB+ for staging, 8GB+ for production
- **Disk:** 50GB+ with SSD preferred
- **Network:** Public IP with DNS A record

## Step 1: Initial Server Setup

### 1.1 Create Deployment User

```bash
# SSH into server as root or sudo user
ssh root@server-ip

# Create deploy user
useradd -m -s /bin/bash deploy
usermod -aG sudo deploy
usermod -aG docker deploy  # Allow docker commands without sudo

# Create .ssh directory
sudo -u deploy mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
```

### 1.2 Configure SSH Key-Based Authentication

On your **local machine**:

```bash
# Generate deployment key (one per server)
ssh-keygen -t ed25519 -f ~/.ssh/anpr-staging-deploy -N "" -C "GitHub Actions Staging Deploy"
# or for older OpenSSH:
ssh-keygen -t rsa -b 4096 -f ~/.ssh/anpr-staging-deploy -N ""

# Output:
# Generating public/private ed25519 key pair.
# Your identification has been saved in /home/user/.ssh/anpr-staging-deploy
# Your public key has been saved in /home/user/.ssh/anpr-staging-deploy.pub
```

Add public key to server:

```bash
# Copy public key to server
cat ~/.ssh/anpr-staging-deploy.pub | ssh deploy@staging-server 'cat >> ~/.ssh/authorized_keys'

# Fix permissions
ssh deploy@staging-server 'chmod 600 ~/.ssh/authorized_keys'

# Test passwordless login
ssh -i ~/.ssh/anpr-staging-deploy deploy@staging-server 'echo "Success!"'
```

### 1.3 Add GitHub Secret

In GitHub repo, add secret `STAGING_DEPLOY_KEY`:

1. Go **Settings → Secrets and variables → Actions → New repository secret**
2. Name: `STAGING_DEPLOY_KEY`
3. Value: Paste contents of `~/.ssh/anpr-staging-deploy` (private key)
4. Click **Add secret**

Repeat for production: `PROD_DEPLOY_KEY` with production server's private key.

---

## Step 2: Install Dependencies

### 2.1 Docker & Docker Compose

```bash
# Update package manager
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker deploy

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify
docker --version
docker-compose --version
```

### 2.2 PostgreSQL Client & Other Tools

```bash
sudo apt-get install -y \
  postgresql-client \
  redis-tools \
  curl \
  git \
  htop \
  vim \
  jq \
  awscli  # If using AWS S3 for backups
```

---

## Step 3: Prepare Deployment Directory

### 3.1 Clone Repository

```bash
sudo -u deploy bash << 'EOF'
cd /opt
git clone https://github.com/YOUR_ORG/anpr.git
cd anpr

# Set origin to use SSH (optional, if repo is private)
git remote set-url origin git@github.com:YOUR_ORG/anpr.git
EOF
```

### 3.2 Create Environment File

```bash
# Staging
sudo bash << 'EOF'
cat > /opt/anpr/.env.staging << 'ENVEOF'
APP_ENV=staging
REGISTRY=ghcr.io
IMAGE_NAME=your-org/anpr/api
IMAGE_TAG=main-latest

POSTGRES_USER=anpr
POSTGRES_PASSWORD=$(openssl rand -base64 32)
POSTGRES_DB=anpr

REDIS_PASSWORD=$(openssl rand -base64 32)

# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
JWT_SECRET=$(openssl rand -base64 32)
SECRET_KEY=$(openssl rand -base64 32)
ENVEOF

chown deploy:deploy /opt/anpr/.env.staging
chmod 600 /opt/anpr/.env.staging
EOF

# Show what was generated
sudo cat /opt/anpr/.env.staging
```

**Save this output securely** (password manager or vault). You'll need it if recovering the server.

### 3.3 Set Proper Permissions

```bash
sudo chown -R deploy:deploy /opt/anpr
sudo chmod 750 /opt/anpr
```

---

## Step 4: Configure GitHub Container Registry Access

```bash
# Create GitHub Personal Access Token (PAT):
# 1. Go https://github.com/settings/tokens
# 2. Click "Generate new token" → "Generate new token (classic)"
# 3. Grant scopes: `read:packages`, `write:packages`
# 4. Copy token

# On deployment server:
sudo -u deploy bash << 'EOF'
docker login ghcr.io
# Username: YOUR_GITHUB_USERNAME
# Password: (paste the PAT token)
EOF

# Save credentials
sudo -u deploy docker config inspect | jq '.Auths["ghcr.io"]'
```

---

## Step 5: Set Up Docker Compose

### 5.1 Add docker-compose.staging.yml

Already committed to repo. Verify:

```bash
sudo -u deploy ls -la /opt/anpr/docker-compose.staging.yml
sudo -u deploy cat /opt/anpr/docker-compose.staging.yml | head -20
```

### 5.2 Create Deployment Script

```bash
sudo bash << 'EOF'
cat > /opt/anpr/deploy-staging.sh << 'DEPLOYEOF'
#!/bin/bash
set -e

DEPLOY_PATH="/opt/anpr"
ENV_FILE="$DEPLOY_PATH/.env.staging"

# Load environment
source $ENV_FILE

cd $DEPLOY_PATH

# Pull latest code
git pull origin main

# Pull latest images
docker-compose -f docker-compose.staging.yml pull api worker

# Start services
docker-compose -f docker-compose.staging.yml up -d api worker

# Wait for API to be healthy
echo "Waiting for API to become healthy..."
for i in {1..30}; do
  if docker-compose -f docker-compose.staging.yml exec -T api curl -f http://localhost:8000/healthz > /dev/null 2>&1; then
    echo "✓ API is healthy"
    docker-compose -f docker-compose.staging.yml ps
    exit 0
  fi
  echo "Attempt $i/30..."
  sleep 2
done

echo "✗ API failed to become healthy"
docker-compose -f docker-compose.staging.yml logs api
exit 1
DEPLOYEOF

chmod +x /opt/anpr/deploy-staging.sh
chown deploy:deploy /opt/anpr/deploy-staging.sh
EOF

# Test the script
sudo -u deploy /opt/anpr/deploy-staging.sh
```

---

## Step 6: Configure Load Balancer (Nginx)

### 6.1 Install Nginx

```bash
sudo apt-get install -y nginx

sudo systemctl start nginx
sudo systemctl enable nginx
```

### 6.2 Create Nginx Configuration

```bash
sudo bash << 'EOF'
cat > /etc/nginx/sites-available/anpr << 'NGINXEOF'
upstream anpr_api {
    # Blue environment (production)
    server localhost:8000;
}

server {
    listen 80;
    server_name staging-api.anpr.internal;  # Change for your domain

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name staging-api.anpr.internal;

    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/staging-api.anpr.internal/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/staging-api.anpr.internal/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Proxy to API
    location / {
        proxy_pass http://anpr_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }

    # Health check endpoint (no logging)
    location /healthz {
        access_log off;
        proxy_pass http://anpr_api;
    }
}
NGINXEOF

# Enable site
ln -sf /etc/nginx/sites-available/anpr /etc/nginx/sites-enabled/anpr
rm -f /etc/nginx/sites-enabled/default

# Test config
nginx -t

# Reload
systemctl reload nginx
EOF
```

### 6.3 Set Up SSL with Let's Encrypt

```bash
sudo apt-get install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --nginx -d staging-api.anpr.internal

# Auto-renewal
sudo systemctl enable certbot.timer
```

---

## Step 7: Configure Monitoring (Optional)

### 7.1 Prometheus

```bash
# Add Prometheus container to docker-compose.prod.yml
sudo bash << 'EOF'
cat >> /opt/anpr/docker-compose.staging.yml << 'PROMEOF'
  prometheus:
    image: prom/prometheus:latest
    container_name: anpr_prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./ops/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    networks:
      - anpr-staging

volumes:
  prometheus_data:
PROMEOF
EOF
```

### 7.2 Node Exporter (Server Metrics)

```bash
sudo bash << 'EOF'
useradd -rs /bin/false node_exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz
tar xvfz node_exporter-*.tar.gz
cp node_exporter-*/node_exporter /usr/local/bin/

cat > /etc/systemd/system/node-exporter.service << 'SYSTEMDEOF'
[Unit]
Description=Prometheus Node Exporter
After=network.target

[Service]
User=node_exporter
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
SYSTEMDEOF

systemctl enable node-exporter
systemctl start node-exporter
EOF
```

---

## Step 8: Automated Backups

### 8.1 PostgreSQL Backup Script

```bash
sudo bash << 'EOF'
cat > /opt/anpr/backup-db.sh << 'BACKUPEOF'
#!/bin/bash
set -e

BACKUP_DIR="/var/backups/anpr"
RETENTION_DAYS=7
DB_CONTAINER="anpr_postgres_staging"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p $BACKUP_DIR

# Dump database
docker exec $DB_CONTAINER pg_dump -U anpr anpr | \
  gzip > $BACKUP_DIR/anpr_db_${TIMESTAMP}.sql.gz

# Upload to S3 (if configured)
# aws s3 cp $BACKUP_DIR/anpr_db_${TIMESTAMP}.sql.gz s3://backups-bucket/anpr/

# Delete old backups (7 days retention)
find $BACKUP_DIR -name "anpr_db_*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_DIR/anpr_db_${TIMESTAMP}.sql.gz"
BACKUPEOF

chmod +x /opt/anpr/backup-db.sh
EOF

# Schedule daily backups at 2 AM
echo "0 2 * * * deploy /opt/anpr/backup-db.sh" | sudo tee -a /etc/crontab
```

---

## Step 9: Verify Deployment

### 9.1 Test Manually

```bash
# SSH into server
ssh -i ~/.ssh/anpr-staging-deploy deploy@staging-server

# Test deployment script
/opt/anpr/deploy-staging.sh

# Check containers
docker-compose -f /opt/anpr/docker-compose.staging.yml ps

# Test API
curl http://localhost:8000/healthz
curl https://staging-api.anpr.internal/healthz
```

### 9.2 Test from GitHub Actions

Merge a small test PR to main:

```bash
git checkout -b test/cicd
echo "# Test commit" >> README.md
git add README.md
git commit -m "Test: CI/CD pipeline"
git push origin test/cicd
```

Open PR, get approval, merge. Watch:
1. CI pipeline passes (lint, test, security, build)
2. Staging deployment triggers automatically
3. Check staging server logs:
   ```bash
   ssh deploy@staging-server
   docker-compose -f /opt/anpr/docker-compose.staging.yml logs -f api
   ```

---

## Troubleshooting

### Issue: `permission denied` during deployment

**Cause:** SSH key permissions wrong

**Fix:**
```bash
ssh deploy@staging-server 'chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
```

### Issue: `docker: command not found`

**Cause:** Docker not installed or user not in docker group

**Fix:**
```bash
sudo gpasswd -a deploy docker
# Then log out and back in
```

### Issue: `cannot pull image: unauthorized`

**Cause:** GitHub Container Registry credentials not configured

**Fix:**
```bash
sudo -u deploy docker logout ghcr.io
sudo -u deploy docker login ghcr.io
# Re-enter PAT token
```

### Issue: `Address already in use` on port 8000

**Cause:** Previous container still running

**Fix:**
```bash
docker-compose -f /opt/anpr/docker-compose.staging.yml down
# Then redeploy
```

---

## Security Hardening

1. **Firewall:** Restrict SSH to GitHub Actions IPs only
   ```bash
   sudo ufw default deny incoming
   sudo ufw allow from 140.82.112.0/20 to any port 22  # GitHub Actions
   sudo ufw allow 80,443/tcp  # HTTP/HTTPS
   ```

2. **SSH:** Disable password auth
   ```bash
   sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
   sudo systemctl restart sshd
   ```

3. **Secrets:** Rotate deployment keys every 90 days

4. **Logging:** Enable Docker logging for audit
   ```bash
   docker run --log-driver json-file --log-opt max-size=10m --log-opt max-file=3
   ```

---

## Related Documentation

- `CICD_SETUP.md` — GitHub Actions workflow configuration
- `RUNBOOK_ROLLBACK.md` — How to rollback production
- `MONITORING.md` — Set up Prometheus/Grafana
