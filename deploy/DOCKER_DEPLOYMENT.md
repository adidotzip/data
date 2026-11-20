# Docker Deployment Guide

Deploy the India Votes Data API using Docker and Docker Compose.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Linux server (Ubuntu 20.04+, Debian 11+, or similar)
- 2GB+ RAM
- 10GB+ disk space

## Quick Start

### 1. Install Docker

**Ubuntu/Debian:**
```bash
# Update package index
sudo apt-get update

# Install dependencies
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Set up stable repository
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add your user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**Other Linux distributions:**
See https://docs.docker.com/engine/install/

### 2. Clone and Configure

```bash
# Clone repository
git clone https://github.com/yourusername/india-votes-data.git
cd india-votes-data

# Create environment file
cp .env.example .env
nano .env
```

**Edit .env:**
```bash
DB_PASSWORD=your_secure_password_here
WORKERS=4
LOG_LEVEL=info
```

### 3. Build and Start

```bash
# Build and start all services
docker compose up -d

# Or build first, then start
docker compose build
docker compose up -d
```

This will start:
- PostgreSQL database (port 5432)
- FastAPI application (port 8000)
- Nginx reverse proxy (ports 80, 443)
- Certbot for SSL (auto-renewal)

### 4. Initialize Database

```bash
# Run database initialization
docker compose exec api python -c "from db import init_db; init_db()"
```

### 5. Verify Deployment

```bash
# Check all services are running
docker compose ps

# Check API health
curl http://localhost:8000/health

# View logs
docker compose logs -f api
```

## Service Management

### Start Services
```bash
docker compose up -d
```

### Stop Services
```bash
docker compose down
```

### Restart Services
```bash
docker compose restart
```

### Stop and Remove Everything (including volumes)
```bash
docker compose down -v
```

### View Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f postgres
docker compose logs -f nginx
```

### Execute Commands in Container
```bash
# Python shell
docker compose exec api python

# Database initialization
docker compose exec api python -c "from db import init_db; init_db()"

# Shell access
docker compose exec api bash
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Database
DB_PASSWORD=secure_password_here

# API Configuration
WORKERS=4                    # Number of Gunicorn workers
LOG_LEVEL=info              # Logging level (debug, info, warning, error)

# Optional
ALLOWED_ORIGINS=*           # CORS origins (comma-separated)
```

### Resource Limits

Edit `docker-compose.yml` to add resource limits:

```yaml
services:
  api:
    # ... existing config ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

## SSL Certificate Setup

### Using Let's Encrypt (Certbot)

1. **Update nginx configuration** with your domain:
```bash
nano deploy/nginx/india-votes-api.conf
# Replace api.yourdomain.com with your actual domain
```

2. **Obtain certificate:**
```bash
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  -d api.yourdomain.com \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email
```

3. **Uncomment HTTPS block** in nginx config:
```bash
nano deploy/nginx/india-votes-api.conf
# Uncomment the SSL server block
```

4. **Reload nginx:**
```bash
docker compose restart nginx
```

### Certificate Renewal

The certbot service automatically renews certificates every 12 hours. To manually renew:

```bash
docker compose run --rm certbot renew
docker compose restart nginx
```

## Database Management

### Backup Database

```bash
# Backup to file
docker compose exec postgres pg_dump -U election_user election_results > backup_$(date +%Y%m%d).sql

# Or using docker
docker compose exec -T postgres pg_dump -U election_user election_results > backup_$(date +%Y%m%d).sql
```

### Restore Database

```bash
# From file
cat backup_20260520.sql | docker compose exec -T postgres psql -U election_user election_results

# Or copy file into container first
docker cp backup_20260520.sql india-votes-db:/tmp/
docker compose exec postgres psql -U election_user election_results -f /tmp/backup_20260520.sql
```

### Access PostgreSQL Shell

```bash
docker compose exec postgres psql -U election_user election_results
```

## Updates and Maintenance

### Update Application Code

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose up -d --build api

# Or rebuild everything
docker compose build --no-cache
docker compose up -d
```

### Update Dependencies

1. Update `requirements.txt`
2. Rebuild image:
```bash
docker compose build --no-cache api
docker compose up -d api
```

### View Resource Usage

```bash
# All containers
docker stats

# Specific container
docker stats india-votes-api
```

### Clean Up

```bash
# Remove stopped containers
docker compose down

# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Complete cleanup (WARNING: removes all unused Docker resources)
docker system prune -a --volumes
```

## Monitoring

### Health Checks

Built-in health checks monitor service health:

```bash
# View health status
docker compose ps

# Check specific service
docker inspect india-votes-api --format='{{.State.Health.Status}}'
```

### Application Logs

```bash
# API logs
docker compose logs -f api

# PostgreSQL logs
docker compose logs -f postgres

# Nginx logs
docker compose logs -f nginx

# All logs with timestamps
docker compose logs -f --timestamps

# Last 100 lines
docker compose logs --tail=100 api
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs api

# Check if port is in use
sudo netstat -tlnp | grep 8000

# Rebuild from scratch
docker compose down -v
docker compose build --no-cache
docker compose up -d
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check database logs
docker compose logs postgres

# Test connection
docker compose exec api python -c "from db import _connect; print(_connect())"
```

### Permission Errors

```bash
# Fix data directory permissions
sudo chown -R 1000:1000 data/

# Or run as root (not recommended)
docker compose exec -u root api chown -R appuser:appuser /app/data
```

### High Memory Usage

```bash
# Check resource usage
docker stats

# Reduce workers in .env
echo "WORKERS=2" >> .env
docker compose up -d api
```

### ChromeDriver Issues

The Docker image includes Chromium and ChromeDriver. If issues persist:

```bash
# Rebuild with latest Chromium
docker compose build --no-cache api
docker compose up -d api
```

## Production Best Practices

### 1. Use Secrets for Sensitive Data

Instead of `.env` file, use Docker secrets:

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt

services:
  postgres:
    secrets:
      - db_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
```

### 2. Resource Limits

Always set resource limits in production:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

### 3. Regular Backups

Set up automated backups with cron:

```bash
# Add to crontab
0 2 * * * docker compose -f /opt/india-votes-data/docker-compose.yml exec -T postgres pg_dump -U election_user election_results > /backups/election_$(date +\%Y\%m\%d).sql
```

### 4. Monitoring

Consider adding monitoring tools:
- Prometheus + Grafana for metrics
- ELK Stack for log aggregation
- Uptime monitoring (UptimeRobot, Pingdom)

### 5. Security

```bash
# Keep Docker updated
sudo apt-get update && sudo apt-get upgrade docker-ce docker-ce-cli

# Scan images for vulnerabilities
docker scan india-votes-data-api

# Use non-root user (already configured in Dockerfile)
```

## Scaling

### Horizontal Scaling (Multiple API Instances)

Edit `docker-compose.yml`:

```yaml
services:
  api:
    # ... existing config ...
    deploy:
      replicas: 3
```

Then:
```bash
docker compose up -d --scale api=3
```

### External Load Balancer

For production, use an external load balancer (HAProxy, Traefik) or cloud load balancer (AWS ELB, GCP Load Balancer).

## Migration from Traditional Deployment

If you have an existing deployment:

1. **Backup database:**
```bash
pg_dump -U election_user election_results > migration_backup.sql
```

2. **Start Docker services:**
```bash
docker compose up -d
```

3. **Restore database:**
```bash
cat migration_backup.sql | docker compose exec -T postgres psql -U election_user election_results
```

4. **Copy data files:**
```bash
cp -r /opt/india-votes-data/data/* ./data/
```

5. **Verify:**
```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/elections
```

## Support

- Docker Documentation: https://docs.docker.com/
- Docker Compose: https://docs.docker.com/compose/
- Project Issues: https://github.com/yourusername/india-votes-data/issues
