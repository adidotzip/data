# Deployment Files

This directory contains all necessary files and configurations for deploying the India Votes Data API to a Linux server.

## Contents

### Configuration Files

- **`nginx/india-votes-api.conf`** - Nginx reverse proxy configuration
- **`systemd/india-votes-api.service`** - Systemd service file for running as a system service

### Scripts

- **`scripts/setup.sh`** - Automated setup script for initial deployment
- **`scripts/update.sh`** - Update script for pulling changes and restarting service
- **`scripts/monitor.sh`** - Health monitoring script

### Docker Files

- **`../Dockerfile`** - Multi-stage Docker build configuration
- **`../docker-compose.yml`** - Docker Compose orchestration file
- **`../.dockerignore`** - Files to exclude from Docker build

### Documentation

- **`DOCKER_DEPLOYMENT.md`** - Complete guide for Docker-based deployment
- **`../DEPLOYMENT.md`** - Complete guide for traditional (systemd) deployment

## Quick Start

Choose one of the following deployment methods:

### Method 1: Traditional Deployment (Systemd + Nginx)

Best for: Single server, full control, traditional Linux deployment

```bash
# Run automated setup
sudo bash scripts/setup.sh

# Or follow manual steps in DEPLOYMENT.md
```

**Pros:**
- Direct system access
- Familiar Linux tools
- Lower resource overhead
- Easy log access

**Cons:**
- More manual configuration
- System dependencies
- Harder to replicate

### Method 2: Docker Deployment

Best for: Containerized environments, easy replication, isolated services

```bash
# Start with Docker Compose
docker compose up -d

# Initialize database
docker compose exec api python -c "from db import init_db; init_db()"
```

**Pros:**
- Isolated environment
- Easy to replicate
- Built-in dependency management
- Simple scaling

**Cons:**
- Requires Docker knowledge
- Slightly higher resource usage
- Additional layer of abstraction

## Deployment Checklist

Before deploying to production:

- [ ] Choose deployment method (Traditional vs Docker)
- [ ] Set up Linux server (Ubuntu 20.04+ recommended)
- [ ] Configure firewall (ports 80, 443, 22)
- [ ] Install prerequisites (see deployment guides)
- [ ] Clone repository to `/opt/india-votes-data`
- [ ] Create and configure `.env` file
- [ ] Set up PostgreSQL database
- [ ] Initialize database schema
- [ ] Configure domain name in Nginx
- [ ] Obtain SSL certificate (Let's Encrypt)
- [ ] Start services
- [ ] Verify health endpoint
- [ ] Test API endpoints
- [ ] Set up monitoring
- [ ] Configure automated backups
- [ ] Set up log rotation

## File Structure

```
deploy/
├── README.md                           # This file
├── DOCKER_DEPLOYMENT.md                # Docker deployment guide
├── nginx/
│   └── india-votes-api.conf            # Nginx configuration
├── systemd/
│   └── india-votes-api.service         # Systemd service
└── scripts/
    ├── setup.sh                        # Automated setup
    ├── update.sh                       # Update script
    └── monitor.sh                      # Monitoring script

Root directory files:
├── Dockerfile                          # Docker build config
├── docker-compose.yml                  # Docker orchestration
├── .dockerignore                       # Docker build exclusions
├── .env.example                        # Environment template
├── requirements.txt                    # Python dependencies
└── DEPLOYMENT.md                       # Main deployment guide
```

## Service Management

### Traditional Deployment (Systemd)

```bash
# Start service
sudo systemctl start india-votes-api

# Stop service
sudo systemctl stop india-votes-api

# Restart service
sudo systemctl restart india-votes-api

# Check status
sudo systemctl status india-votes-api

# View logs
sudo journalctl -u india-votes-api -f

# Enable auto-start on boot
sudo systemctl enable india-votes-api
```

### Docker Deployment

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart services
docker compose restart

# View logs
docker compose logs -f

# Check status
docker compose ps
```

## Monitoring

### Health Check

```bash
# Traditional
curl http://localhost:8000/health

# Docker
curl http://localhost:8000/health
# or
docker compose exec api curl http://localhost:8000/health
```

### Using Monitor Script

```bash
bash deploy/scripts/monitor.sh
```

### Manual Monitoring

```bash
# CPU and Memory
top -p $(pgrep -f "india-votes-api")

# Active connections
netstat -an | grep :8000 | grep ESTABLISHED

# Disk usage
df -h /opt/india-votes-data

# Log errors
sudo journalctl -u india-votes-api --since "1 hour ago" | grep -i error
```

## Backup and Recovery

### Database Backup

**Traditional (PostgreSQL):**
```bash
pg_dump -U election_user election_results > backup_$(date +%Y%m%d).sql
```

**Docker:**
```bash
docker compose exec -T postgres pg_dump -U election_user election_results > backup_$(date +%Y%m%d).sql
```

### Data Files Backup

```bash
tar -czf data_backup_$(date +%Y%m%d).tar.gz /opt/india-votes-data/data
```

### Automated Backups (Cron)

Add to `/etc/crontab`:

```bash
# Daily database backup at 2 AM
0 2 * * * postgres pg_dump election_results > /backups/election_$(date +\%Y\%m\%d).sql

# Weekly full backup on Sundays at 3 AM
0 3 * * 0 root tar -czf /backups/full_backup_$(date +\%Y\%m\%d).tar.gz /opt/india-votes-data
```

## Troubleshooting

### Service Won't Start

```bash
# Check detailed logs
sudo journalctl -u india-votes-api -xe

# Check port availability
sudo lsof -i :8000

# Check permissions
ls -la /opt/india-votes-data
```

### Database Connection Errors

```bash
# Test PostgreSQL connection
psql -U election_user -d election_results -h localhost

# Check PostgreSQL status
sudo systemctl status postgresql

# View PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

### High Resource Usage

```bash
# Check resource usage
htop

# Reduce workers
# Edit .env or systemd service file
# Reduce --workers value

# Restart service
sudo systemctl restart india-votes-api
```

## Security Recommendations

1. **Firewall**: Only allow necessary ports (80, 443, 22)
2. **SSL/TLS**: Always use HTTPS in production
3. **Database**: Use strong passwords, restrict network access
4. **Updates**: Keep system and dependencies updated
5. **Secrets**: Never commit `.env` or credentials to git
6. **Monitoring**: Set up alerts for service failures
7. **Backups**: Automate and test recovery procedures
8. **Logs**: Implement log rotation and monitoring

## Performance Tuning

### Worker Processes

Adjust based on CPU cores:
- Formula: `(2 × CPU_cores) + 1`
- 2-core server: 5 workers
- 4-core server: 9 workers

**Traditional:**
Edit `/etc/systemd/system/india-votes-api.service`:
```ini
--workers 5
```

**Docker:**
Edit `.env`:
```bash
WORKERS=5
```

### Database Connection Pool

Edit PostgreSQL config:
```bash
sudo nano /etc/postgresql/*/main/postgresql.conf

# Adjust based on worker count
max_connections = 100
shared_buffers = 256MB
```

### Nginx Caching

Add to nginx config:
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g;
proxy_cache api_cache;
proxy_cache_valid 200 5m;
```

## Getting Help

- **Main Documentation**: See [../DEPLOYMENT.md](../DEPLOYMENT.md)
- **Docker Guide**: See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
- **Issues**: Open an issue on GitHub
- **Logs**: Check service logs for error details

## Version History

- **v2.0.0** - Docker support, production-ready deployment
- **v1.0.0** - Initial deployment configuration
